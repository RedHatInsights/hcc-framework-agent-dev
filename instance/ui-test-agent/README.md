# UI Testing Agent

Jira-driven UI exploration and readiness reporting for Hybrid Cloud Console.

## Configuration

- `agent/instance.yaml` selects the custom Jira workflow and browser runtime.
- `agent/targets.json` sets the shared dev, stage, and prod targets and supports app-specific overrides. Ephemeral-environment tickets provide their own URL.
- Set `BOT_CONFIG_PATH=instance/ui-test-agent` and a stable, unique `BOT_INSTANCE_ID` for this deployment.
- Set `BOT_LABEL` to the dedicated Jira intake label. The initial proposed value is `hcc-ui-test`.
- Provide the deployment's `JIRA_MCP_URL`; the framework supplies shared memory and Chromium through the `browser` runtime environment.
- Configure test-account access and the approved production test org through the deployment's secure configuration. Do not put credentials in this repo or Jira.

Before production mutation tests, configure the production test-org identifier for the relevant application. The workflow pauses instead of guessing when a target or safe access boundary is missing.

The agent posts its report to the original Jira issue, does not transition Jira status, and tracks prior test runs in the shared memory server.

## Local configuration location

Use `BOT_CONFIG_PATH=instance/ui-test-agent` for this instance. The config root contains the `agent/` directory loaded by the runner.

See [PLANNING.md](PLANNING.md) for the readiness rubric, report structure, and implementation decisions.

Copy the ready-to-use [Jira request template](JIRA-REQUEST-TEMPLATE.md) into new UI testing tickets. The agent can work from a rough description; requesters do not need to write formal acceptance criteria or test cases.
