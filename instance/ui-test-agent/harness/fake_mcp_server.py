"""Optional loopback FastMCP servers backed by the same disposable fixtures."""

from __future__ import annotations

import argparse
import os

from fake_services import FakeJira, FakeMemory


def memory_tasks_payload(service: FakeMemory, query) -> dict:
    """Mirror the read-only task-list REST endpoint used by preflight helpers."""
    instance_id = query.get("instance_id")
    items = service.call(
        "task_list",
        {"include_archived": True, "instance_id": instance_id},
    )
    if hasattr(query, "getlist"):
        excluded = set(query.getlist("exclude_status"))
    else:
        raw_excluded = query.get("exclude_status", [])
        excluded = set(
            raw_excluded if isinstance(raw_excluded, list) else [raw_excluded]
        )
    items = [task for task in items if task.get("status") not in excluded]
    return {"items": items}


def create_server(kind: str):
    """Build the selected local Jira or memory MCP server."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit(
            "The dev-bot Python environment is required. Run with: "
            "uv run --project dev-bot --extra dev python "
            "instance/ui-test-agent/harness/fake_mcp_server.py ..."
        ) from exc

    if kind == "jira":
        service = FakeJira([_fixture_issue()])
        mcp = FastMCP("ui-test-fake-jira")
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        @mcp.custom_route("/__harness/state", methods=["GET"])
        async def jira_state(_request: Request):
            return JSONResponse(service.snapshot())

        @mcp.tool()
        def jira_search(jql: str, fields: str = "", limit: int = 20) -> dict:
            return service.call(
                "jira_search", {"jql": jql, "fields": fields, "limit": limit}
            )

        @mcp.tool()
        def jira_get_issue(
            issue_key: str, fields: str = "", comment_limit: int = 100
        ) -> dict | None:
            return service.call(
                "jira_get_issue",
                {
                    "issue_key": issue_key,
                    "fields": fields,
                    "comment_limit": comment_limit,
                },
            )

        @mcp.tool()
        def jira_add_comment(issue_key: str, comment: str) -> dict:
            return service.call(
                "jira_add_comment", {"issue_key": issue_key, "comment": comment}
            )

        return mcp

    if kind == "memory":
        service = FakeMemory()
        mcp = FastMCP("ui-test-fake-memory")
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        @mcp.custom_route("/__harness/state", methods=["GET"])
        async def memory_state(_request: Request):
            return JSONResponse(service.snapshot())

        @mcp.custom_route("/api/tasks", methods=["GET"])
        async def api_tasks(request: Request):
            return JSONResponse(memory_tasks_payload(service, request.query_params))

        @mcp.custom_route("/api/cycle-runs", methods=["POST"])
        async def record_cycle_run(request: Request):
            record = await request.json()
            record["transcript_present"] = bool(record.pop("transcript_b64", None))
            service.cycle_runs.append(record)
            return JSONResponse({"id": f"local-cycle-{len(service.cycle_runs)}"})

        @mcp.custom_route("/api/costs", methods=["POST"])
        async def record_cost(request: Request):
            service.costs.append(await request.json())
            return JSONResponse({"stored": True})

        @mcp.custom_route("/api/bot-status", methods=["POST"])
        async def record_status(request: Request):
            service.status_updates.append(await request.json())
            return JSONResponse({"stored": True})

        @mcp.custom_route("/api/instances/{instance_id}", methods=["GET"])
        async def get_idle_state(request: Request):
            value = service.idle_states.get(request.path_params["instance_id"])
            return JSONResponse(value or {"idle_consecutive_cycles": 0})

        @mcp.custom_route("/api/instances/{instance_id}/idle", methods=["PATCH"])
        async def update_idle_state(request: Request):
            instance_id = request.path_params["instance_id"]
            service.idle_states[instance_id] = await request.json()
            return JSONResponse({"stored": True})

        @mcp.tool()
        def task_list(
            status: str | None = None,
            include_archived: bool = False,
            instance_id: str | None = None,
        ) -> list[dict]:
            return service.call(
                "task_list",
                {
                    "status": status,
                    "include_archived": include_archived,
                    "instance_id": instance_id,
                },
            )

        @mcp.tool()
        def task_get(external_key: str, source_type: str = "jira") -> dict | None:
            return service.call(
                "task_get", {"external_key": external_key, "source_type": source_type}
            )

        @mcp.tool()
        def task_check_capacity(instance_id: str | None = None) -> dict:
            return service.call("task_check_capacity", {"instance_id": instance_id})

        @mcp.tool()
        def bot_status_update(
            state: str,
            message: str,
            external_key: str | None = None,
            repo: str | None = None,
            instance_id: str | None = None,
        ) -> dict:
            return service.call(
                "bot_status_update",
                {
                    "state": state,
                    "message": message,
                    "external_key": external_key,
                    "repo": repo,
                    "instance_id": instance_id,
                },
            )

        @mcp.tool()
        def task_add(
            external_key: str,
            repo: str,
            branch: str,
            status: str = "in_progress",
            source_type: str = "jira",
            title: str | None = None,
            summary: str | None = None,
            metadata: dict | None = None,
            instance_id: str | None = None,
        ) -> dict:
            return service.call(
                "task_add",
                {
                    "external_key": external_key,
                    "repo": repo,
                    "branch": branch,
                    "status": status,
                    "source_type": source_type,
                    "title": title,
                    "summary": summary,
                    "metadata": metadata,
                    "instance_id": instance_id,
                },
            )

        @mcp.tool()
        def task_update(
            external_key: str,
            source_type: str = "jira",
            status: str | None = None,
            last_addressed: str | None = None,
            paused_reason: str | None = None,
            title: str | None = None,
            summary: str | None = None,
            metadata: dict | None = None,
        ) -> dict | None:
            return service.call(
                "task_update",
                {
                    "external_key": external_key,
                    "source_type": source_type,
                    "status": status,
                    "last_addressed": last_addressed,
                    "paused_reason": paused_reason,
                    "title": title,
                    "summary": summary,
                    "metadata": metadata,
                },
            )

        @mcp.tool()
        def memory_store(
            category: str,
            title: str,
            content: str,
            repo: str | None = None,
            external_key: str | None = None,
            source_type: str | None = None,
            tags: list[str] | None = None,
            metadata: dict | None = None,
        ) -> dict:
            return service.call(
                "memory_store",
                {
                    "category": category,
                    "title": title,
                    "content": content,
                    "repo": repo,
                    "external_key": external_key,
                    "source_type": source_type,
                    "tags": tags,
                    "metadata": metadata,
                },
            )

        @mcp.tool()
        def memory_search(
            query: str,
            category: str | None = None,
            repo: str | None = None,
            tag: str | None = None,
            limit: int = 5,
        ) -> list[dict]:
            return service.call(
                "memory_search",
                {
                    "query": query,
                    "category": category,
                    "repo": repo,
                    "tag": tag,
                    "limit": limit,
                },
            )

        @mcp.tool()
        def memory_list() -> list[dict]:
            return service.call("memory_list", {})

        return mcp

    raise ValueError(f"Unsupported fake MCP service: {kind}")


def _fixture_issue() -> dict:
    profile_alias = os.environ.get("UI_HARNESS_PROFILE", "viewer")
    target_mode = os.environ.get("UI_HARNESS_TARGET", "local")
    if target_mode == "stage":
        environment = "stage"
        target_url = "https://console.stage.redhat.com"
        application = "Hybrid Cloud Console"
        goal = "Explore the Subscriptions and Inventory views in the configured test account."
        expected = (
            "The configured test profile can authenticate, the active account and org context are clear, "
            "and both views render without changing data."
        )
        scope = "Read-only exploration only. Do not create, edit, or delete data."
    else:
        environment = "ephemeral"
        target_url = "http://127.0.0.1:8765"
        application = "Hybrid Cloud Console local fixture"
        goal = "Explore the signed-in console and check the Subscriptions and Inventory views."
        expected = "The requested profile can sign in; both views open and show their fixture content."
        scope = "No production data or mutations are in scope."
    return {
        "key": "UITEST-LOCAL-1",
        "fields": {
            "summary": f"Explore the {environment} console using the UI test harness",
            "description": (
                f"Application: {application}\n"
                f"Environment: {environment}\n"
                f"Target URL: {target_url}\n"
                f"Test profile alias: {profile_alias}\n"
                f"Goal: {goal}\n"
                f"Expected: {expected}\n"
                f"Scope: {scope}"
            ),
            "status": {"name": "To Do"},
            "labels": ["ui-test"],
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z",
            "issuetype": {"name": "Task"},
        },
        "comments": [],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("jira", "memory"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("fake MCP servers may bind only to loopback")
    port = args.port or (8766 if args.kind == "jira" else 8767)
    mcp = create_server(args.kind)
    print(f"Starting local fake {args.kind} MCP at http://{args.host}:{port}/mcp")
    import uvicorn

    uvicorn.run(
        mcp.streamable_http_app(),
        host=args.host,
        port=port,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
