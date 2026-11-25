"""Alias-based loopback HTTP bridge for the Stage Chromium session."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TypedDict
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

TARGET_URL = "https://console.stage.redhat.com"
LOGIN_SCRIPT = Path(__file__).with_name("browser-login.mjs")
PORT = int(os.environ.get("UI_TEST_LOGIN_HELPER_PORT", "8768"))
CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
BROWSER_LOGIN_TIMEOUT_SECONDS = 240
PROFILE_DIR = Path("/tmp/ui-test-chromium")
password_submission_at: float | None = None
PASSWORD_RETRY_COOLDOWN_SECONDS = 300
login_lock = threading.Lock()
CREDENTIALS_DIR = Path(
    os.environ.pop("UI_TEST_CREDENTIALS_DIR", "") or "/var/run/ui-test-credentials"
)
ALIAS_PATTERN = re.compile(r"[A-Za-z0-9:_-]{1,80}\Z")
PUBLIC_MESSAGES = {
    "blocked": "The login helper could not prepare or access Stage sign-in.",
    "sign_in_form_not_found": (
        "The standard Red Hat SSO login form did not appear. Report the sign-in "
        "blocker."
    ),
    "login_unconfirmed": (
        "The SSO helper could not confirm Stage sign-in. Do not assume "
        "authentication or retry."
    ),
    "authentication_failed": (
        "Red Hat SSO rejected the configured test account. Do not retry."
    ),
    "authenticated": (
        "Stage loaded and the signed-in User Avatar control is visible. Verify "
        "the account and org context."
    ),
}
SIGN_IN_INCOMPLETE = {
    "status": "blocked",
    "message": "The login helper could not complete the Stage sign-in flow.",
    "credential_submission_started": True,
}
DIAGNOSTIC_PHASES = frozenset(
    {
        "validate_configuration",
        "launch_browser",
        "prepare_browser",
        "navigate_to_stage",
        "wait_for_sso_form",
        "submit_credentials",
        "verify_stage_session",
        "transfer_session",
    }
)
DIAGNOSTIC_CODES = frozenset(
    {
        "missing_login_configuration",
        "proxy_configuration_missing",
        "browser_page_missing",
        "sso_form_missing",
        "sso_rejected_credentials",
        "proxy_lockdown",
        "stage_return_missing",
        "signed_in_marker_missing_after_sso",
        "signed_in_marker_confirmed",
        "sso_flow_error",
        "browser_preparation_error",
        "login_deadline_exceeded",
        "browser_process_unhandled",
        "password_submission_cooldown",
        "credential_profile_unavailable",
        "node_runtime_unavailable",
        "browser_child_failed",
        "browser_child_timed_out",
        "browser_child_io_error",
        "browser_child_invalid_result",
        "chromium_not_found",
        "proxy_configuration_missing",
        "chromium_exited_before_ready",
        "chromium_devtools_timeout",
        "runtime_dependency_missing",
        "startup_started",
        "chromium_ready",
        "helper_runtime_error",
        "authenticated_without_submission",
    }
)
DIAGNOSTIC_EVENTS = frozenset(
    {
        "startup",
        "startup_failed",
        "chromium_ready",
        "http_server_starting",
        "login_result",
        "helper_runtime_failed",
    }
)


class LoginResult(TypedDict, total=False):
    status: str
    message: str
    profile_alias: str
    credential_submission_started: bool
    diagnostic_code: str
    diagnostic_phase: str


def _log_diagnostic(
    event: str,
    *,
    status: str,
    reason_code: str,
    phase: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Write structured diagnostics without credentials, aliases, or raw errors."""
    record = {
        "component": "stage-login-helper",
        "event": event if event in DIAGNOSTIC_EVENTS else "helper_runtime_failed",
        "status": status,
        "reason_code": (
            reason_code
            if reason_code in DIAGNOSTIC_CODES
            else "browser_child_invalid_result"
        ),
    }
    if phase in DIAGNOSTIC_PHASES:
        record["phase"] = phase
    if duration_ms is not None:
        record["duration_ms"] = max(0, duration_ms)
    print(json.dumps(record, separators=(",", ":")), file=sys.stderr, flush=True)


def _credentials_for(alias: str) -> tuple[str, str] | None:
    """Resolve a profile inside the helper, never from a request credential."""
    if not ALIAS_PATTERN.fullmatch(alias):
        return None

    try:
        username = (
            (CREDENTIALS_DIR / f"{alias}.username")
            .read_text(encoding="utf-8")
            .rstrip("\r\n")
        )
        password = (
            (CREDENTIALS_DIR / f"{alias}.password")
            .read_text(encoding="utf-8")
            .rstrip("\r\n")
        )
    except OSError:
        return None
    if not username or not password:
        return None
    return username, password


def _public_login_result(payload: object) -> LoginResult:
    """Allow only known statuses and fixed messages from the browser process."""
    if not isinstance(payload, dict):
        return {"status": "blocked", "message": PUBLIC_MESSAGES["blocked"]}

    status = payload.get("status")
    if not isinstance(status, str) or status not in PUBLIC_MESSAGES:
        return {"status": "blocked", "message": PUBLIC_MESSAGES["blocked"]}

    return {
        "status": status,
        "message": PUBLIC_MESSAGES[status],
        "credential_submission_started": bool(
            payload.get("credential_submission_started", False)
        ),
    }


async def health(_request: Request) -> JSONResponse:
    if await asyncio.to_thread(_chromium_cdp_ready):
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "browser_unavailable"}, status_code=503)


async def sign_in_endpoint(request: Request) -> JSONResponse:
    """Accept only a configured profile alias; never accept credential fields."""
    try:
        body = await request.body()
        if len(body) > 256:
            raise ValueError("request body too large")
        payload = json.loads(body)
    except ValueError:
        return JSONResponse(
            {"status": "blocked", "message": "Request must contain one profile alias."},
            status_code=400,
        )

    if (
        not isinstance(payload, dict)
        or set(payload) != {"alias"}
        or not isinstance(payload["alias"], str)
    ):
        return JSONResponse(
            {"status": "blocked", "message": "Request must contain one profile alias."},
            status_code=400,
        )

    result = await asyncio.to_thread(sign_in, payload["alias"])
    return JSONResponse(result)


def _sign_in(alias: str) -> LoginResult:
    """Sign in with a configured persona alias, never accepting credentials.

    The helper resolves the alias from its private credential source. Password
    submissions are rate-limited to prevent rapid model retries.
    """
    global password_submission_at
    started_at = time.monotonic()
    reason_code: str
    phase: str | None = None
    if (
        password_submission_at is not None
        and started_at - password_submission_at < PASSWORD_RETRY_COOLDOWN_SECONDS
    ):
        result = {
            "status": "blocked",
            "message": "A password was submitted recently. Stop this request and continue on a later cycle.",
        }
        reason_code = "password_submission_cooldown"
    else:
        credentials = _credentials_for(alias)
        if credentials is None:
            result = {
                "status": "blocked",
                "message": "No credentials are configured for that profile alias.",
            }
            reason_code = "credential_profile_unavailable"
        else:
            node = shutil.which("node")
            if not node:
                result = {
                    "status": "blocked",
                    "message": "Node.js is unavailable to the login helper.",
                }
                reason_code = "node_runtime_unavailable"
            else:
                result = _run_browser_login(node, *credentials)
                reason_code = result.pop(
                    "diagnostic_code", "browser_child_invalid_result"
                )
                phase = result.pop("diagnostic_phase", None)
                submission_started = bool(
                    result.pop("credential_submission_started", False)
                )
                status = result.get("status")
                if status == "authenticated":
                    if not submission_started:
                        result = {
                            "status": "login_unconfirmed",
                            "message": PUBLIC_MESSAGES["login_unconfirmed"],
                        }
                        reason_code = "authenticated_without_submission"
                    else:
                        result["profile_alias"] = alias
                if status == "authentication_failed" or submission_started:
                    password_submission_at = time.monotonic()

    _log_diagnostic(
        "login_result",
        status=result.get("status", "blocked"),
        reason_code=reason_code,
        phase=phase,
        duration_ms=int((time.monotonic() - started_at) * 1000),
    )
    return result


def _browser_child_failure(
    reason_code: str, *, credential_submission_started: bool
) -> LoginResult:
    failure: LoginResult = dict(SIGN_IN_INCOMPLETE)
    failure["credential_submission_started"] = credential_submission_started
    failure["diagnostic_code"] = reason_code
    return failure


def _run_browser_login(node: str, username: str, password: str) -> LoginResult:
    """Run the isolated browser flow and retain only allowlisted diagnostics."""
    helper_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "UI_TEST_USERNAME": username,
        "UI_TEST_PASSWORD": password,
        "UI_TEST_TARGET_URL": TARGET_URL,
        "UI_TEST_CDP_URL": CDP_URL,
        "UI_BROWSER_PROXY": os.environ.get("UI_BROWSER_PROXY", ""),
        "PLAYWRIGHT_BROWSERS_PATH": os.environ.get(
            "PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"
        ),
    }
    process = None
    try:
        process = subprocess.Popen(
            [node, str(LOGIN_SCRIPT)],
            env=helper_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        stdout, _ = process.communicate(timeout=BROWSER_LOGIN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        if process is not None:
            try:
                process.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()
        return _browser_child_failure(
            "browser_child_timed_out", credential_submission_started=True
        )
    except OSError:
        return _browser_child_failure(
            "browser_child_io_error", credential_submission_started=False
        )

    try:
        payload = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        return _browser_child_failure(
            "browser_child_invalid_result", credential_submission_started=True
        )
    status = payload.get("status") if isinstance(payload, dict) else None
    if (
        process.returncode != 0
        or not isinstance(status, str)
        or status not in PUBLIC_MESSAGES
    ):
        return _browser_child_failure(
            "browser_child_failed", credential_submission_started=True
        )

    safe_result = _public_login_result(payload)
    default_codes = {
        "blocked": "browser_preparation_error",
        "sign_in_form_not_found": "sso_form_missing",
        "login_unconfirmed": "sso_flow_error",
        "authentication_failed": "sso_rejected_credentials",
        "authenticated": "signed_in_marker_confirmed",
    }
    diagnostic_code = payload.get("diagnostic_code")
    safe_result["diagnostic_code"] = (
        diagnostic_code
        if isinstance(diagnostic_code, str) and diagnostic_code in DIAGNOSTIC_CODES
        else default_codes[status]
    )
    diagnostic_phase = payload.get("diagnostic_phase")
    if isinstance(diagnostic_phase, str) and diagnostic_phase in DIAGNOSTIC_PHASES:
        safe_result["diagnostic_phase"] = diagnostic_phase
    return safe_result


def sign_in(alias: str) -> LoginResult:
    """Serialize requests so concurrent calls cannot submit credentials twice."""
    with login_lock:
        return _sign_in(alias)


def _chromium_cdp_ready() -> bool:
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(f"{CDP_URL}/json/version", timeout=1) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def _find_chromium() -> str | None:
    browser_path = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    if not browser_path.is_dir():
        return None
    return next(
        (
            str(candidate)
            for candidate in sorted(browser_path.rglob("chrome"))
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        None,
    )


class HelperStartupError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _start_chromium(profile_dir: Path) -> subprocess.Popen | None:
    """Start Chromium with the instance proxy, without changing shared presets."""
    if _chromium_cdp_ready():
        return None

    chrome = _find_chromium()
    if not chrome:
        raise HelperStartupError("chromium_not_found")
    proxy = os.environ.get("UI_BROWSER_PROXY", "").strip()
    if not proxy:
        raise HelperStartupError("proxy_configuration_missing")

    command = [
        chrome,
        "--headless",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--disable-sync",
        "--disable-extensions",
        "--disable-popup-blocking",
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        "--ignore-certificate-errors",
        "--host-resolver-rules=MAP consent.trustarc.com 127.0.0.1",
        "--proxy-bypass-list=localhost;127.0.0.1;::1",
        f"--user-data-dir={profile_dir / 'profile'}",
        f"--proxy-server={proxy}",
    ]

    browser_env = {
        key: os.environ[key]
        for key in ("HOME", "LANG", "LC_ALL", "PATH", "PLAYWRIGHT_BROWSERS_PATH")
        if os.environ.get(key)
    }
    browser_env["HOME"] = str(profile_dir)
    process = subprocess.Popen(
        command,
        env=browser_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise HelperStartupError("chromium_exited_before_ready")
        if _chromium_cdp_ready():
            return process
        time.sleep(1)

    process.terminate()
    process.wait(timeout=5)
    raise HelperStartupError("chromium_devtools_timeout")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("stage login helper may bind only to loopback")
    try:
        import uvicorn
    except ImportError:
        _log_diagnostic(
            "startup_failed", status="error", reason_code="runtime_dependency_missing"
        )
        raise SystemExit(1)

    _log_diagnostic("startup", status="starting", reason_code="startup_started")
    browser = None
    try:
        # A fixed path prevents abandoned profiles from accumulating after restarts.
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        PROFILE_DIR.mkdir(parents=True)
        browser = _start_chromium(PROFILE_DIR)
        _log_diagnostic("chromium_ready", status="ready", reason_code="chromium_ready")
        _log_diagnostic(
            "http_server_starting", status="starting", reason_code="startup_started"
        )
        uvicorn.run(
            Starlette(
                routes=[
                    Route("/health", health),
                    Route("/sign-in", sign_in_endpoint, methods=["POST"]),
                ]
            ),
            host=args.host,
            port=args.port,
            access_log=False,
            log_level="warning",
        )
    except HelperStartupError as error:
        _log_diagnostic("startup_failed", status="error", reason_code=error.reason_code)
        raise SystemExit(1)
    except Exception:
        _log_diagnostic(
            "helper_runtime_failed", status="error", reason_code="helper_runtime_error"
        )
        raise SystemExit(1)
    finally:
        if browser and browser.poll() is None:
            browser.terminate()
            browser.wait(timeout=10)
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
