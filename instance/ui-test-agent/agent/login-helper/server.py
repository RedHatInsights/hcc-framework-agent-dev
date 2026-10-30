"""Alias-based loopback HTTP bridge for the Stage Chromium session."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import TypedDict
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

TARGET_URL = "https://console.stage.redhat.com"
LOGIN_SCRIPT = Path(__file__).with_name("browser-login.mjs")
PORT = 8768
mcp = FastMCP("stage-login-helper")
password_submission_at: float | None = None
PASSWORD_RETRY_COOLDOWN_SECONDS = 300
login_lock = threading.Lock()
USERNAME = os.environ.pop("UI_TEST_USERNAME", "")
PASSWORD = os.environ.pop("UI_TEST_PASSWORD", "")
HARNESS_ALIAS = os.environ.pop("UI_HARNESS_PROFILE", "")
CREDENTIALS_DIR = Path(
    os.environ.pop("UI_TEST_CREDENTIALS_DIR", "") or "/var/run/ui-test-credentials"
)
ALIAS_PATTERN = re.compile(r"[A-Za-z0-9:_-]{1,80}\Z")
PUBLIC_MESSAGES = {
    "blocked": "The login helper could not prepare or access Stage sign-in.",
    "already_authenticated": (
        "Stage already shows the signed-in User Avatar control. Verify the account "
        "and org context."
    ),
    "authentication_unconfirmed": (
        "Stage loaded without a confirmed signed-in User Avatar control. Do not "
        "assume authentication."
    ),
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


class LoginResult(TypedDict, total=False):
    status: str
    message: str
    profile_alias: str


attempts: list[LoginResult] = []


def _credentials_for(alias: str) -> tuple[str, str] | None:
    """Resolve a profile inside the helper, never from a request credential."""
    if not ALIAS_PATTERN.fullmatch(alias):
        return None

    if USERNAME or PASSWORD:
        if USERNAME and PASSWORD and alias == HARNESS_ALIAS:
            return USERNAME, PASSWORD
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


def _is_configured_alias(alias: str) -> bool:
    """Return whether an alias is safe to echo in tool output and harness state."""
    if not ALIAS_PATTERN.fullmatch(alias):
        return False
    if USERNAME or PASSWORD:
        return bool(USERNAME and PASSWORD and alias == HARNESS_ALIAS)
    return (CREDENTIALS_DIR / f"{alias}.username").is_file() and (
        CREDENTIALS_DIR / f"{alias}.password"
    ).is_file()


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


@mcp.custom_route("/__harness/state", methods=["GET"])
async def state(_request: Request) -> JSONResponse:
    return JSONResponse({"attempts": attempts})


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    if await asyncio.to_thread(_chromium_cdp_ready):
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "browser_unavailable"}, status_code=503)


@mcp.custom_route("/sign-in", methods=["POST"])
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
    now = time.monotonic()
    credentials = _credentials_for(alias)
    if (
        password_submission_at is not None
        and now - password_submission_at < PASSWORD_RETRY_COOLDOWN_SECONDS
    ):
        result = {
            "status": "blocked",
            "message": "A password was submitted recently. Stop this request and continue on a later cycle.",
        }
    elif credentials is None:
        result = {
            "status": "blocked",
            "message": "No credentials are configured for that profile alias.",
        }
    else:
        username, password = credentials
        node = shutil.which("node")
        if not node:
            result = {
                "status": "blocked",
                "message": "Node.js is unavailable to the login helper.",
            }
        else:
            helper_env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                "UI_TEST_USERNAME": username,
                "UI_TEST_PASSWORD": password,
                "UI_TEST_TARGET_URL": TARGET_URL,
                "UI_HARNESS_SHOW_COOKIE_PROMPT": os.environ.get(
                    "UI_HARNESS_SHOW_COOKIE_PROMPT", ""
                ),
            }
            try:
                completed = subprocess.run(
                    [node, str(LOGIN_SCRIPT)],
                    env=helper_env,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=100,
                )
                payload = (
                    json.loads(completed.stdout) if completed.stdout.strip() else {}
                )
                public_payload = _public_login_result(payload)
                status = public_payload.get("status")
                submission_started = bool(
                    public_payload.pop("credential_submission_started", False)
                )
                if status in {"authenticated", "already_authenticated"}:
                    password_submission_at = None
                elif status == "authentication_failed":
                    password_submission_at = time.monotonic()
                elif submission_started:
                    password_submission_at = time.monotonic()
                valid_status = (
                    isinstance(payload, dict)
                    and isinstance(payload.get("status"), str)
                    and payload["status"] in PUBLIC_MESSAGES
                )
                if completed.returncode == 0 and valid_status:
                    result = public_payload
                else:
                    password_submission_at = time.monotonic()
                    result = {
                        "status": "blocked",
                        "message": "The login helper could not complete the stage sign-in flow.",
                    }
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                password_submission_at = time.monotonic()
                result = {
                    "status": "blocked",
                    "message": "The login helper could not complete the stage sign-in flow.",
                }

    safe_result: LoginResult = dict(result)
    if _is_configured_alias(alias):
        safe_result["profile_alias"] = alias
    attempts.append(safe_result)
    return safe_result


def sign_in(alias: str) -> LoginResult:
    """Serialize requests so concurrent calls cannot submit credentials twice."""
    with login_lock:
        return _sign_in(alias)


def _chromium_cdp_ready() -> bool:
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open("http://127.0.0.1:9222/json/version", timeout=1) as response:
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


def _start_chromium(profile_dir: Path | None = None) -> subprocess.Popen | None:
    """Start Chromium with the instance proxy, without changing shared presets."""
    if _chromium_cdp_ready():
        return None

    chrome = _find_chromium()
    if not chrome:
        raise RuntimeError("The login helper could not find Playwright Chromium.")
    proxy = os.environ.get("UI_BROWSER_PROXY", "").strip()
    if not proxy:
        raise RuntimeError(
            "UI_BROWSER_PROXY must be set before the helper starts Chromium."
        )

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
        "--remote-debugging-port=9222",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        "--ignore-certificate-errors",
        "--host-resolver-rules=MAP consent.trustarc.com 127.0.0.1",
        "--proxy-bypass-list=localhost;127.0.0.1;::1",
        f"--user-data-dir={profile_dir / 'profile' if profile_dir else '/tmp/ui-test-chromium-profile'}",
        f"--proxy-server={proxy}",
    ]

    browser_env = {
        key: os.environ[key]
        for key in ("HOME", "LANG", "LC_ALL", "PATH", "PLAYWRIGHT_BROWSERS_PATH")
        if os.environ.get(key)
    }
    if profile_dir:
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
            raise RuntimeError(
                "Chromium exited before its DevTools endpoint became ready."
            )
        if _chromium_cdp_ready():
            return process
        time.sleep(1)

    process.terminate()
    process.wait(timeout=5)
    raise RuntimeError("Chromium DevTools did not become ready within 60 seconds.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("stage login helper may bind only to loopback")
    import uvicorn

    # Keep the browser profile and session cookies in the helper's ephemeral /tmp mount.
    profile_dir = Path(tempfile.mkdtemp(prefix="ui-test-chromium-", dir="/tmp"))
    browser = None
    try:
        browser = _start_chromium(profile_dir)
        uvicorn.run(
            mcp.streamable_http_app(),
            host=args.host,
            port=args.port,
            access_log=False,
            log_level="warning",
        )
    finally:
        if browser and browser.poll() is None:
            browser.terminate()
            browser.wait(timeout=10)
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
