# UI Testing Agent

Jira-driven UI exploration and readiness reporting for Hybrid Cloud Console.

## Configuration

- `agent/instance.yaml` selects the custom Jira workflow and browser runtime.
- `agent/targets.json` sets `https://console.stage.redhat.com` as the initial shared stage target and supports app-specific overrides. Dev and prod mappings are not configured yet. Ephemeral-environment tickets provide their own URL.
- Set `BOT_LABEL` to the dedicated Jira intake label. The initial proposed value is `hcc-ui-test`.
- Configure browser access and the approved production test org through the deployment's existing secure configuration. Do not put credentials in this repo or Jira.

The agent posts its report to the original Jira issue, does not transition Jira status, and tracks prior test runs in the shared memory server.

## Local configuration location

Use `BOT_CONFIG_PATH=instance/ui-test-agent` for this instance. The config root contains the `agent/` directory loaded by the runner.

See [PLANNING.md](PLANNING.md) for the intake template, readiness rubric, report structure, and implementation decisions.
