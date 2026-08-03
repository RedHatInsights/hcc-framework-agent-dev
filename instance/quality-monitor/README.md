# Quality Monitor Instance

Automated daily scans for:
1. **Merge violations** - PRs merged with failed CI checks
2. **Test anti-patterns** - Hard-coded sleeps, disabled tests, missing assertions

Creates JIRA tickets + Slack notifications. Runs daily at 9 AM via KEDA cron.

## Configuration

**Required files:**
- `instance.yaml` - Workflow config
- `project-repos.json` - Repos to monitor + JIRA project mapping
- `mcp.json` - MCP server connections
- `workflows/quality-monitor/` - Workflow implementation

**JIRA setup** (`project-repos.json`):
```json
{
  "_config": {
    "jira": {
      "default_project": "RHCLOUD",
      "repo_mapping": {"special-repo": "SPECIALPROJ"}
    }
  }
}
```

Ticket types:
- Merge violations → Bug (High/Medium priority)
- Test anti-patterns → Task (Medium/High based on count)

**Anti-patterns** (`workflows/quality-monitor/anti-patterns.yaml`):
- Detection patterns, severity levels, remediation guidance

**Team context** (`CLAUDE.md`):
- Slack channel, high-priority repos, escalation contacts

## Local Testing

```bash
# Test preflight scripts
cd instance/quality-monitor/agent/workflows/quality-monitor/preflight
uv sync --extra dev
uv run pytest

# Run full workflow
export BOT_CONFIG_PATH=instance/quality-monitor
export BOT_INSTANCE_ID=quality-monitor-local
make run
```

## Deployment

1. Merge PR → Konflux rebuilds image
2. Get image SHA from Quay
3. Add to app-interface:
```yaml
resourceTemplates:
  - name: devbot-quality-monitor
    parameters:
      BOT_CONFIG_PATH: instance/quality-monitor
      BOT_REPLICAS: '0'  # KEDA scales on schedule
```
4. Configure KEDA:
```yaml
triggers:
  - type: cron
    metadata:
      timezone: "America/New_York"
      start: "0 9 * * 1-5"  # 9 AM weekdays
      desiredReplicas: "1"
```

## Verification

```bash
oc get deployment devbot-quality -n <namespace>
oc get scaledobject devbot-quality-cron-scaler
oc logs -f deployment/devbot-quality
```

## Troubleshooting

**No JIRA tickets created:**
- Check JIRA MCP server connection
- Verify thresholds met (FAILURE for merge, 3+ HIGH for tests)
- Check task memory for duplicates

**No Slack notifications:**
- Verify `SLACK_WEBHOOK_URL` set
- Check thresholds (all merges, 5+ HIGH test patterns)

**Anti-patterns not detected:**
- Test patterns locally: `grep -E 'pattern' test/file.spec.ts`
- Check repo cloned in pod
- Verify test file patterns in `test-config.yaml`

## Customization

**Add anti-pattern:**
```yaml
# anti-patterns.yaml
hardcoded_urls:
  regex: '(https?://)(staging|prod)\.(company\.com)'
  severity: medium
  message: "Hardcoded environment URL"
```

**Exclude noisy repo:**
```yaml
# anti-patterns.yaml
scan_settings:
  excluded_repos:
    - legacy-app
```

**Adjust thresholds:**
```yaml
notification_thresholds:
  high_severity_threshold: 5  # Reduce noise
```
