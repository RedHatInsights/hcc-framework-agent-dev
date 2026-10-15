"""Local-only MCP bridge that submits stage account credentials through CDP."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

HARNESS_DIR = Path(__file__).resolve().parent
TARGET_URL = "https://console.stage.redhat.com"
LOGIN_SCRIPT = HARNESS_DIR / "stage-login-cdp.mjs"
PORT = 8768
mcp = FastMCP("stage-login-helper")
attempts: list[dict] = []
password_submission_attempted = False
USERNAME = os.environ.pop("UI_TEST_USERNAME", "")
PASSWORD = os.environ.pop("UI_TEST_PASSWORD", "")
PROFILE_ALIAS = os.environ.pop("UI_HARNESS_PROFILE", "viewer")


@mcp.custom_route("/__harness/state", methods=["GET"])
async def state(_request: Request):
    return JSONResponse({"attempts": attempts})


@mcp.tool()
def sign_in() -> dict:
    """Submit the configured stage account once after the login form is ready.

    Credentials come from this local helper's environment and are never
    accepted as tool arguments or returned to the caller. A second call is
    allowed only if the earlier call stopped before a password submission.
    """
    global password_submission_attempted
    username = USERNAME
    password = PASSWORD
    alias = PROFILE_ALIAS
    if password_submission_attempted:
        result = {
            "status": "blocked",
            "message": "A password submission already ran in this cycle; credentials will not be submitted again.",
        }
    elif not username or not password:
        result = {
            "status": "blocked",
            "message": "Stage test credentials are not configured in the local helper.",
        }
    else:
        node = shutil.which("node")
        if not node:
            result = {
                "status": "blocked",
                "message": "Node.js is unavailable to the local login helper.",
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
                password_submission_attempted = bool(
                    payload.pop("credential_submission_started", False)
                )
                if completed.returncode == 0 and payload.get("status"):
                    result = payload
                else:
                    password_submission_attempted = True
                    result = {
                        "status": "blocked",
                        "message": "The local login helper could not complete the stage sign-in flow.",
                    }
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                password_submission_attempted = True
                result = {
                    "status": "blocked",
                    "message": "The local login helper could not complete the stage sign-in flow.",
                }

    safe_result = {"profile_alias": alias, **result}
    attempts.append(safe_result)
    return safe_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("stage login helper may bind only to loopback")
    import uvicorn

    uvicorn.run(
        mcp.streamable_http_app(),
        host=args.host,
        port=args.port,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
