"""Run one UI-testing agent cycle against disposable loopback fixtures."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener


HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parents[2]
DEV_BOT_DIR = REPO_ROOT / "dev-bot"
INSTANCE_AGENT_DIR = REPO_ROOT / "instance" / "ui-test-agent" / "agent"
INSTANCE_ID = "ui-test-harness"
LABEL = "ui-test"
TARGET_URLS = {
    "stage": "https://console.stage.redhat.com",
    "local": "http://127.0.0.1:8765",
}
PORTS = {
    "hcc": 8765,
    "jira": 8766,
    "memory": 8767,
    "login": 8768,
    "chrome": 9222,
    "metrics": 9091,
}
MODEL_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_SKIP_VERTEX_AUTH",
    "ANTHROPIC_VERTEX_BASE_URL",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "UI_HARNESS_MODEL",
    "CLOUD_ML_REGION",
    "VERTEX_LOCATION",
)


def _model_environment(parent: dict[str, str]) -> dict[str, str]:
    api_key_ready = bool(parent.get("ANTHROPIC_API_KEY"))
    vertex_ready = (
        parent.get("CLAUDE_CODE_USE_VERTEX", "").lower() in {"1", "true"}
        and parent.get("CLAUDE_CODE_SKIP_VERTEX_AUTH", "").lower() in {"1", "true"}
        and bool(parent.get("ANTHROPIC_VERTEX_BASE_URL"))
        and bool(parent.get("ANTHROPIC_VERTEX_PROJECT_ID"))
    )
    if not api_key_ready and not vertex_ready:
        raise RuntimeError(
            "Set ANTHROPIC_API_KEY, or configure the Vertex proxy with "
            "CLAUDE_CODE_USE_VERTEX, CLAUDE_CODE_SKIP_VERTEX_AUTH, "
            "ANTHROPIC_VERTEX_BASE_URL, and ANTHROPIC_VERTEX_PROJECT_ID."
        )
    return {name: parent[name] for name in MODEL_ENV_VARS if parent.get(name)}


def _check_ports_free(target: str):
    busy = []
    names = ("jira", "memory", "chrome", "metrics")
    if target == "local":
        names += ("hcc",)
    else:
        names += ("login",)
    for name in names:
        port = PORTS[name]
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                busy.append(f"{name} ({port})")
    if busy:
        raise RuntimeError("Harness ports already in use: " + ", ".join(busy))


def _python_runtime() -> Path:
    python = DEV_BOT_DIR / ".venv" / "bin" / "python"
    required = "import claude_agent_sdk, mcp.server.fastmcp, uvicorn"
    if python.is_file():
        check = subprocess.run(
            [str(python), "-c", required], capture_output=True, text=True
        )
        if check.returncode == 0:
            return python

    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("Install uv and prepare the dev-bot Python environment.")
    print("Preparing the dev-bot Python environment (one-time setup)...", flush=True)
    subprocess.run(
        [
            uv,
            "sync",
            "--project",
            str(DEV_BOT_DIR),
            "--extra",
            "dev",
            "--no-install-workspace",
        ],
        check=True,
    )
    if not python.is_file():
        raise RuntimeError("uv did not create dev-bot/.venv/bin/python")
    return python


def _find_chromium() -> str:
    candidates = [os.environ.get("CHROME_BIN", "")]
    candidates.extend(
        shutil.which(name) or ""
        for name in ("chromium", "chromium-browser", "google-chrome")
    )
    candidates.extend(
        [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/opt/homebrew/bin/chromium",
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise RuntimeError(
        "Could not find Chromium. Set CHROME_BIN to its executable path."
    )


def _write_runtime(
    workspace: Path, model: dict[str, str], max_turns: int, timeout: int, target: str
):
    runtime = workspace / "dev-bot"
    runtime.mkdir()
    for name in ("bot", "presets", ".claude"):
        shutil.copytree(DEV_BOT_DIR / name, runtime / name)
    for name in ("config.json", "project-repos.json"):
        source = DEV_BOT_DIR / name
        if source.is_file():
            shutil.copy2(source, runtime / name)

    config_path = runtime / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["claude"]["model"] = model.get("UI_HARNESS_MODEL", config["claude"]["model"])
    config["claude"]["maxTurns"] = max_turns
    config["claude"]["cycleTimeoutSeconds"] = max(30, timeout - 15)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    chrome_command = shutil.which("chrome-devtools-mcp")
    if not chrome_command:
        raise RuntimeError(
            "Install Chrome DevTools MCP once with: npm install --global chrome-devtools-mcp"
        )
    command, args = chrome_command, []
    args.extend(["--browserUrl", "http://127.0.0.1:9222", "--acceptInsecureCerts"])
    mcp_config = {
        "mcpServers": {
            "chrome-devtools": {"command": command, "args": args},
            "bot-memory": {"type": "http", "url": "http://127.0.0.1:8767/mcp"},
        }
    }
    if target == "stage":
        mcp_config["mcpServers"]["stage-login"] = {
            "type": "http",
            "url": "http://127.0.0.1:8768/mcp",
        }
    (runtime / ".mcp.json").write_text(
        json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8"
    )

    if target == "stage":
        config_module = runtime / "bot" / "config.py"
        config_text = config_module.read_text(encoding="utf-8")
        config_text, count = re.subn(
            r'(?m)^    "mcp__bot-memory__\*",$',
            '    "mcp__stage-login__sign_in",\n    "mcp__bot-memory__*",',
            config_text,
        )
        if count != 1:
            raise RuntimeError("Could not enable the one local stage-login tool")
        config_module.write_text(config_text, encoding="utf-8")

    config_repo = workspace / "config-repo"
    profile = config_repo / "ui-test-agent"
    profile.mkdir(parents=True)
    shutil.copytree(INSTANCE_AGENT_DIR, profile / "agent")
    instance_yaml = profile / "agent" / "instance.yaml"
    text = instance_yaml.read_text(encoding="utf-8")
    text, count = re.subn(r"(?m)^source:\s*.*$", "source: run_and_exit", text)
    if count != 1:
        raise RuntimeError("Could not set the local instance source to run_and_exit")
    instance_yaml.write_text(text, encoding="utf-8")
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git is required to create the disposable config overlay")
    subprocess.run(
        [git, "init", "-q", str(config_repo)], check=True, capture_output=True
    )
    subprocess.run(
        [git, "-C", str(config_repo), "config", "user.name", "UI Harness"], check=True
    )
    subprocess.run(
        [git, "-C", str(config_repo), "config", "user.email", "ui-harness@localhost"],
        check=True,
    )
    subprocess.run([git, "-C", str(config_repo), "add", "ui-test-agent"], check=True)
    subprocess.run(
        [git, "-C", str(config_repo), "commit", "-qm", "Create local one-cycle config"],
        check=True,
    )
    return runtime, config_repo


def _base_environment(home: Path, python: Path) -> dict[str, str]:
    return {
        "PATH": os.pathsep.join([str(python.parent), os.environ.get("PATH", "")]),
        "HOME": str(home),
        "TMPDIR": os.environ.get("TMPDIR", tempfile.gettempdir()),
        "LANG": "C.UTF-8",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "no_proxy": "127.0.0.1,localhost,::1",
    }


def _start(
    name: str, command: list[str], cwd: Path, env: dict[str, str], artifacts: Path
):
    log = (artifacts / f"{name}.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return process, log


def _http_json(url: str, method="GET", body=None, timeout=2):
    opener = build_opener(ProxyHandler({}))
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(
        url, data=payload, method=method, headers={"Content-Type": "application/json"}
    )
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read())


def _wait_for_http(url: str, process: subprocess.Popen, name: str, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"{name} exited while starting; inspect its log in the results directory"
            )
        try:
            _http_json(url)
            return
        except (URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
            time.sleep(0.2)
    raise RuntimeError(
        f"Timed out starting {name}; inspect its log in the results directory"
    )


def _stop(processes: list[subprocess.Popen]):
    for process in reversed(processes):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for process in reversed(processes):
        if process.poll() is None:
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)


def _redact(value, secrets: list[str]):
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item, secrets) for key, item in value.items()}
    return value


def _capture_state(artifacts: Path, secrets: list[str], target: str) -> dict:
    state = {}
    endpoints = {
        "jira": "http://127.0.0.1:8766/__harness/state",
        "memory": "http://127.0.0.1:8767/__harness/state",
    }
    if target == "local":
        endpoints["hcc"] = "http://127.0.0.1:8765/__harness/state"
    else:
        endpoints["stage_login"] = "http://127.0.0.1:8768/__harness/state"
    for name, url in endpoints.items():
        try:
            state[name] = _http_json(url)
        except Exception as exc:
            state[name] = {"capture_error": type(exc).__name__}

    serialized = json.dumps(state)
    credential_leak = any(secret and secret in serialized for secret in secrets)
    state = _redact(state, secrets)
    (artifacts / "state.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )
    return {"state": state, "credential_leak_detected": credential_leak}


def _sanitize_artifacts(artifacts: Path, secrets: list[str]) -> bool:
    """Redact fixture credentials from persisted text artifacts."""
    leaked = False
    text_suffixes = {".json", ".jsonl", ".log", ".md", ".txt"}
    for path in artifacts.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(secret and secret in original for secret in secrets):
            leaked = True
            path.write_text(_redact(original, secrets), encoding="utf-8")
    return leaked


def _extract_report(jira_state: dict) -> tuple[list[dict], str | None]:
    reports = []
    for issue in jira_state.get("issues", {}).values():
        comments = issue.get("comments", [])
        for comment in comments:
            body = comment.get("body", "")
            if isinstance(body, str) and "UI Testing Agent Report" in body:
                reports.append({"issue_key": issue.get("key"), "body": body})
    readiness = None
    if reports:
        match = re.search(
            r"UI test report\s*[—-]\s*(Ready with risks|Ready|Not ready|Inconclusive)",
            reports[-1]["body"],
            re.I,
        )
        readiness = match.group(1) if match else None
    return reports, readiness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-model", action="store_true", help="Confirm one external model cycle"
    )
    parser.add_argument(
        "--target",
        choices=tuple(TARGET_URLS),
        default=os.environ.get("UI_HARNESS_TARGET", "stage"),
        help="UI target mode (default: stage; choose local for the loopback fixture)",
    )
    parser.add_argument(
        "--profile", default=os.environ.get("UI_HARNESS_PROFILE", "viewer")
    )
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if not args.allow_model:
        parser.error("pass --allow-model to explicitly enable the model call")
    if args.max_turns < 1 or args.max_turns > 100:
        parser.error("--max-turns must be between 1 and 100")
    if args.timeout < 60:
        parser.error("--timeout must be at least 60 seconds")
    if args.target == "local" and args.profile not in {"viewer", "org-admin"}:
        parser.error("local target profile must be viewer or org-admin")
    if args.target == "stage" and not re.fullmatch(
        r"[A-Za-z0-9:_-]{1,80}", args.profile
    ):
        parser.error("stage --profile must be a non-secret profile alias")

    parent_env = dict(os.environ)
    if args.target == "stage":
        username = parent_env.get("UI_TEST_USERNAME", "")
        password = parent_env.get("UI_TEST_PASSWORD", "")
        if not username or not password:
            parser.error("stage mode requires UI_TEST_USERNAME and UI_TEST_PASSWORD")
        secrets = [username, password]
        if shutil.which("node") is None:
            parser.error(
                "stage mode requires Node.js 22+ for the local credential helper"
            )
    else:
        username = parent_env.get("UI_HARNESS_USERNAME", "")
        password = parent_env.get("UI_HARNESS_PASSWORD", "")
        if bool(username) != bool(password):
            parser.error("set both UI_HARNESS_USERNAME and UI_HARNESS_PASSWORD")
        secrets = [username, password]
    if args.target == "local" and not username and not password:
        profiles = json.loads(
            (HARNESS_DIR / "fake-auth" / "profiles.json").read_text(encoding="utf-8")
        )
        secrets.extend(
            [profiles[args.profile]["username"], profiles[args.profile]["password"]]
        )
    model_env = _model_environment(parent_env)
    _check_ports_free(args.target)
    chromium = _find_chromium()
    python = _python_runtime()

    started_at = datetime.now(UTC).isoformat()
    artifacts = Path(tempfile.mkdtemp(prefix="ui-test-agent-results-"))
    workspace = Path(tempfile.mkdtemp(prefix="ui-test-agent-work-"))
    processes: list[subprocess.Popen] = []
    log_handles = []
    print(
        f"Starting one {args.target} model cycle. Jira and memory use local fixtures; "
        f"the browser target is {TARGET_URLS[args.target]}.",
        flush=True,
    )
    print(f"Results directory: {artifacts}", flush=True)

    try:
        config_repo = workspace / "config-repo"
        runtime, config_repo = _write_runtime(
            workspace, model_env, args.max_turns, args.timeout, args.target
        )
        home = workspace / "home"
        home.mkdir()
        base_env = _base_environment(home, python)

        if args.target == "local":
            hcc_env = {
                **base_env,
                "UI_HARNESS_PROFILE": args.profile,
                "UI_HARNESS_USERNAME": username,
                "UI_HARNESS_PASSWORD": password,
            }
            hcc, log = _start(
                "hcc",
                [str(python), str(HARNESS_DIR / "fake-hcc" / "server.py")],
                REPO_ROOT,
                hcc_env,
                artifacts,
            )
            processes.append(hcc)
            log_handles.append(log)
            _wait_for_http("http://127.0.0.1:8765/__harness/state", hcc, "fake HCC")

        for service, port in (("jira", 8766), ("memory", 8767)):
            service_env = {**base_env}
            if service == "jira":
                service_env["UI_HARNESS_PROFILE"] = args.profile
                service_env["UI_HARNESS_TARGET"] = args.target
            process, log = _start(
                service,
                [
                    str(python),
                    str(HARNESS_DIR / "fake_mcp_server.py"),
                    service,
                    "--port",
                    str(port),
                ],
                REPO_ROOT,
                service_env,
                artifacts,
            )
            processes.append(process)
            log_handles.append(log)
            _wait_for_http(
                f"http://127.0.0.1:{port}/__harness/state", process, f"fake {service}"
            )

        browser_home = workspace / "browser-home"
        browser_home.mkdir()
        browser_env = {
            "PATH": base_env["PATH"],
            "HOME": str(browser_home),
            "TMPDIR": base_env["TMPDIR"],
            "LANG": "C.UTF-8",
        }
        chrome_log = (artifacts / "chromium.log").open("w", encoding="utf-8")
        log_handles.append(chrome_log)
        chrome_proxy = (
            "http://squid.corp.redhat.com:3128"
            if args.target == "stage"
            else "direct://"
        )
        chrome_target = TARGET_URLS[args.target]
        chrome = subprocess.Popen(
            [
                chromium,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--no-first-run",
                "--disable-sync",
                "--disable-extensions",
                f"--proxy-server={chrome_proxy}",
                "--proxy-bypass-list=localhost;127.0.0.1;::1",
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=9222",
                "--remote-allow-origins=*",
                f"--user-data-dir={workspace / 'chromium-profile'}",
                chrome_target,
            ],
            cwd=workspace,
            env=browser_env,
            stdout=chrome_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(chrome)
        _wait_for_http("http://127.0.0.1:9222/json/version", chrome, "Chromium")

        if args.target == "stage":
            login_env = {
                **base_env,
                "UI_HARNESS_PROFILE": args.profile,
                "UI_TEST_USERNAME": username,
                "UI_TEST_PASSWORD": password,
            }
            login, log = _start(
                "stage-login",
                [str(python), str(HARNESS_DIR / "stage-login-server.py")],
                REPO_ROOT,
                login_env,
                artifacts,
            )
            processes.append(login)
            log_handles.append(log)
            _wait_for_http(
                "http://127.0.0.1:8768/__harness/state", login, "stage login helper"
            )

        bot_env = {
            **base_env,
            **model_env,
            "BOT_CONFIG_REPO": str(config_repo),
            "BOT_CONFIG_PATH": "ui-test-agent",
            "BOT_LABEL": LABEL,
            "BOT_INSTANCE_ID": INSTANCE_ID,
            "JIRA_MCP_URL": "http://127.0.0.1:8766/mcp",
            "BOT_MEMORY_URL": "http://127.0.0.1:8767/mcp",
            "MEMORY_API_URL": "http://127.0.0.1:8767/api",
            "COSTS_API_URL": "http://127.0.0.1:8767/api/costs",
            "CYCLE_RUNS_API_URL": "http://127.0.0.1:8767/api/cycle-runs",
            "BOT_DASHBOARD_URL": "http://127.0.0.1:8767/api/bot-status",
            "PLAYWRIGHT_BROWSERS_PATH": str(Path(chromium).parent),
        }
        provider = (
            "Vertex proxy"
            if model_env.get("CLAUDE_CODE_USE_VERTEX")
            else "Anthropic API"
        )
        print(f"Model provider: configured {provider}", flush=True)

        runner_log = (artifacts / "runner.log").open("w", encoding="utf-8")
        log_handles.append(runner_log)
        runner = subprocess.Popen(
            [
                str(python),
                "-m",
                "bot.run",
                "--label",
                LABEL,
                "--instance-id",
                INSTANCE_ID,
            ],
            cwd=runtime,
            env=bot_env,
            stdout=runner_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(runner)
        try:
            runner_exit = runner.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(runner.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                runner.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(runner.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                runner.wait(timeout=5)
            runner_exit = 124
        for handle in log_handles:
            handle.flush()

        captured = _capture_state(artifacts, secrets, args.target)
        state = captured["state"]
        reports, readiness = _extract_report(state.get("jira", {}))
        fixture_authenticated = any(
            event.get("alias") == args.profile
            for event in state.get("hcc", {}).get("login_events", [])
        )
        stage_login_attempts = state.get("stage_login", {}).get("attempts", [])
        stage_login_attempted = any(
            attempt.get("status") for attempt in stage_login_attempts
        )
        learned = any(
            item.get("external_key") == "UITEST-LOCAL-1"
            and item.get("source_type") == "jira"
            for item in state.get("memory", {}).get("memories", [])
        )
        snapshot = {
            "started_at": started_at,
            "runner_exit_code": runner_exit,
            "profile_alias": args.profile,
            "report_count": len(reports),
            "readiness": readiness,
            "target_mode": args.target,
            "target_url": chrome_target,
            "login_events": state.get("hcc", {}).get("login_events", []),
            "stage_login_attempts": stage_login_attempts,
            "authenticated_as_expected_profile": (
                fixture_authenticated if args.target == "local" else None
            ),
            "stage_login_helper_invoked": stage_login_attempted,
            "memory_record_created": learned,
            "credential_leak_detected": captured["credential_leak_detected"],
            "agent_report": reports[-1] if reports else None,
        }
        runtime_log = runtime / "data" / "bot.log"
        if runtime_log.is_file():
            shutil.copy2(runtime_log, artifacts / "bot.log")
        costs = runtime / "data" / "costs.jsonl"
        if costs.is_file():
            shutil.copy2(costs, artifacts / "costs.jsonl")
        transcript_dir = home / ".claude" / "projects"
        if transcript_dir.is_dir():
            shutil.copytree(
                transcript_dir, artifacts / "transcripts", dirs_exist_ok=True
            )

        credential_leak = captured["credential_leak_detected"] or _sanitize_artifacts(
            artifacts, secrets
        )
        snapshot["credential_leak_detected"] = credential_leak
        (artifacts / "summary.json").write_text(
            json.dumps(_redact(snapshot, secrets), indent=2) + "\n", encoding="utf-8"
        )
        passed = (
            runner_exit == 0
            and bool(reports)
            and (
                fixture_authenticated
                if args.target == "local"
                else stage_login_attempted
            )
            and learned
            and not credential_leak
        )
        print(
            f"Cycle {'completed' if passed else 'did not meet harness checks'}; readiness: {readiness or 'missing'}."
        )
        print(
            f"Inspect Jira report, tool calls, memory, logs, and transcript under {artifacts}"
        )
        return 0 if passed else 1
    finally:
        _stop(processes)
        for handle in log_handles:
            try:
                handle.close()
            except Exception:
                pass
        if artifacts.exists():
            _sanitize_artifacts(artifacts, secrets)
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Harness could not start: {exc}", file=sys.stderr)
        raise SystemExit(2)
