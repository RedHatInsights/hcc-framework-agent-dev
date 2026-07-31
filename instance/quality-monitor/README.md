# Quality Monitor Instance

Automated code quality monitoring workflow for detecting:
1. **Merge violations** - PRs merged with failed CI checks
2. **Test anti-patterns** - Hard-coded sleeps, disabled tests, missing assertions

## Overview

This instance runs on a scheduled basis (daily at 9 AM) via KEDA cron scaling. It scans configured repositories and creates JIRA tickets + Slack notifications for quality violations. Created tickets can be consumed by other bot workflows for remediation.

## Configuration

### Required Files

- `instance.yaml` - Workflow and environment preset configuration
- `project-repos.json` - Repositories to monitor (includes JIRA project mapping)
- `mcp.json` - MCP server connections (Jira, memory server)
- `workflows/quality-monitor/` - The workflow implementation

### JIRA Configuration

The `project-repos.json` file includes a `_config` section for JIRA settings:

```json
{
  "_config": {
    "jira": {
      "default_project": "RHCLOUD",
      "repo_mapping": {
        "special-repo": "SPECIALPROJ"
      }
    }
  }
}
```

- `default_project`: JIRA project key to use for all tickets (default: RHCLOUD)
- `repo_mapping`: Optional per-repo overrides for specific repositories

Quality violations will create tickets in the configured JIRA project:
- **Merge violations**: Bug tickets with High/Medium priority
- **Test anti-patterns**: Task tickets with Medium/High priority based on severity

### Anti-Pattern Configuration

Edit `workflows/quality-monitor/anti-patterns.yaml` to customize:
- Detection patterns (regex)
- Severity levels (high/medium/low)
- Remediation guidance
- Notification thresholds
- Excluded repos

### Team-Specific Context

Edit `CLAUDE.md` (this directory) to configure:
- Slack channel for notifications
- High-priority repositories
- Escalation contacts
- Repository-specific rules

## Testing Locally

### Test Preflight Scripts

```bash
cd /path/to/rehor

# Set up Python path
export PYTHONPATH=presets/shared/preflight:.claude/skills

# Test merge check script
python3 instance/quality-monitor/agent/workflows/quality-monitor/preflight/01-check-merged-prs.py

# Test anti-pattern scanner
python3 instance/quality-monitor/agent/workflows/quality-monitor/preflight/02-scan-test-anti-patterns.py
```

### Test Anti-Pattern Regex

```bash
# Test a regex pattern against a test file
grep -E 'your-regex-pattern' path/to/test/file.test.js
```

### Test Workflow Locally

```bash
# Run the full bot instance
export BOT_CONFIG_PATH=instance/quality-monitor
export BOT_INSTANCE_ID=quality-monitor-local
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...
export GH_TOKEN=ghp_...

# Run manually
make run
```

## Deployment

### 1. Merge to Main Branch

After PR review, merge your changes. The existing Konflux pipeline will automatically rebuild the image.

### 2. Get Image SHA

```bash
# Wait for Konflux build, then get the SHA
# Check Quay: quay.io/redhat-services-prod/.../hcc-framework-agent-dev
```

### 3. Add to App-Interface

In your deploy.yml (e.g., `data/services/insights/platform-frontend-ai-dev/deploy.yml`):

```yaml
resourceTemplates:
# ... existing instances ...

- name: devbot-quality-monitor
  path: /deploy/template.yaml
  url: https://github.com/RedHatInsights/hcc-framework-agent-dev
  targets:
  - namespace:
      $ref: /services/insights/platform-frontend-ai-dev/namespaces/stage.hcmais01ue1.yml
    ref: <merge-commit-sha>
    parameters:
      BOT_IMAGE_TAG: <merge-commit-sha>
      BOT_IMAGE: quay.io/redhat-services-prod/hcc-platex-services/hcc-framework-agent-dev
      BOT_NAME: devbot-quality
      BOT_INSTANCE_ID: quality-monitor
      BOT_CONFIG_PATH: instance/quality-monitor
      BOT_REPLICAS: '0'
      BOT_LABEL: quality-monitor
      GCP_PROJECT_ID: <same-as-other-instances>
      GCP_REGION: global
      VERTEX_ALLOWED_MODELS: claude-sonnet-4-6,claude-opus-4-6
      BOT_CONFIG_REPO: https://github.com/RedHatInsights/hcc-framework-agent-dev.git
      SLACK_WEBHOOK_URL: <your-webhook-url>
```

### 4. Configure KEDA Schedule

Ensure your deploy template includes KEDA ScaledObject. Customize the schedule if needed:

```yaml
# In deploy/template.yaml or as parameter override
triggers:
- type: cron
  metadata:
    timezone: "America/New_York"
    start: "0 9 * * 1-5"  # Daily at 9 AM, weekdays only
    end: "10 9 * * 1-5"   # Run for 10 minutes
    desiredReplicas: "1"
```

## Verification

After app-interface MR merges:

```bash
# Check deployment exists
oc get deployment devbot-quality -n <namespace>

# Check pod is using correct config
oc get deployment devbot-quality -o yaml | grep BOT_CONFIG_PATH
# Should show: instance/quality-monitor

# Wait for scheduled time, then check logs
oc logs -f deployment/devbot-quality

# Check KEDA scaler
oc get scaledobject devbot-quality-cron-scaler -o yaml
```

## Monitoring

### Check for Issues

```bash
# See memory server dashboard
# http://devbot-memory-server:8080

# Check tasks created by this instance
# Filter by instance_id: quality-monitor

# Check Slack notifications sent
# Look in configured channel
```

### Metrics to Track

Via memory server API or dashboard:
- Violations detected per day
- JIRA tickets created (check task memory)
- Slack notifications sent
- Team response times (JIRA ticket age)
- Remediation rates (ticket closure rate)

## Troubleshooting

### Preflight Scripts Not Running

- Check KEDA schedule is active
- Verify pod is scaled up during scan window
- Check preflight script time gating (9 AM only)

### No JIRA Tickets Created

- Verify JIRA MCP server is connected (check mcp.json)
- Check task memory for duplicate detection (may skip if already created)
- Check capacity isn't full: max 10 active tasks
- Verify threshold met (FAILURE for merge violations, 3+ HIGH for test anti-patterns)

### No Slack Notifications

- Verify SLACK_WEBHOOK_URL is set
- Test webhook: `curl -X POST -H 'Content-Type: application/json' -d '{"text":"test"}' $SLACK_WEBHOOK_URL`
- Check bot reached notification threshold (5+ HIGH issues)

### Anti-Patterns Not Detected

- Test regex locally with grep
- Verify test directories exist in cloned repos
- Check repos are being cloned (look in `repos/` directory in pod)
- Increase max_findings_per_pattern in anti-patterns.yaml

## Adding Custom Skills

If you need custom skills (e.g., for specialized notifications):

1. Create skill directory: `instance/quality-monitor/agent/skills/my-skill/`
2. Add `SKILL.md` with usage instructions
3. Add Python script managed via `uv` (see rehor skill development docs)
4. Register in workflow manifest.yaml

## Customization Examples

### Add New Anti-Pattern

Edit `workflows/quality-monitor/anti-patterns.yaml`:

```yaml
anti_patterns:
  hardcoded_urls:
    regex: '(https?://)(staging|prod)\.(yourcompany\.com)'
    severity: medium
    message: "Hardcoded environment URL in test"
    recommendation: "Use environment variable for base URL"
```

### Exclude Noisy Repos

Edit `workflows/quality-monitor/anti-patterns.yaml`:

```yaml
scan_settings:
  excluded_repos:
    - legacy-app  # Too many issues, low value
    - third-party-integration  # External code
```

### Change Notification Thresholds

Edit `workflows/quality-monitor/anti-patterns.yaml`:

```yaml
notification_thresholds:
  high_severity_threshold: 5  # Increase to reduce noise
  slack_high_threshold: 10
```

## Links

- [Rehor Docs](https://github.com/OpenShift-Fleet/rehor)
- [Custom Workflows Guide](https://github.com/OpenShift-Fleet/rehor/blob/master/docs/presets/custom-workflows.md)
- [Custom Preflight Scripts](https://github.com/OpenShift-Fleet/rehor/blob/master/docs/presets/custom-preflight.md)
