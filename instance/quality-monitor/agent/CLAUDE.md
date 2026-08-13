# Quality Monitor Instance - Team Context

Instance-specific configuration supplementing workflow CLAUDE.md.

## Team Settings

- **Slack**: #platform-quality
- **High-priority repos**: insights-chrome, rbac-service, platform-ui
- **Escalation**: @platform-lead
- **Timezone**: America/New_York
- **Hours**: 9 AM - 5 PM ET

## Notification Rules

**Slack (when to send):**
- All merge violations
- 5+ HIGH test anti-patterns
- Repeat offenders (3+ in 30 days)

**JIRA tickets (when to create):**
- FAILURE merge violations
- 3+ HIGH test anti-patterns
- Repeat offenders

**Labels:** quality, ci-failure (merges), tech-debt (tests), testing

**Assignment:** Tag team from CODEOWNERS, let team self-assign

## High-Priority Overrides

For high-priority repos above:
- Create tickets for any severity
- Notify on all findings
- Tag escalation contact for HIGH

## False Positives

If team marks "won't fix":
1. Note in memory (repo + pattern + reason)
2. Skip duplicate issues for same pattern
3. Still track for trends
4. Re-evaluate quarterly

## Tracking

Memory stores:
- Issue creation/response times
- Team response patterns
- Remediation times (HIGH severity)
- Repeat offender trends

Use to identify:
- Repos/teams needing education
- Most common patterns
- Remediation effectiveness

## Schedule

Daily 9 AM ET via KEDA:
- `scan_only_repos` whitelist for merge violations (24h window)
- `scan_only_repos` whitelist for anti-patterns (rotates, max 3 per scan)

Both checks share the `scan_only_repos` list in `test-config.yaml`.

## Custom Patterns

Edit `anti-patterns.yaml`:
```yaml
hardcoded_env_url:
  regex: '(staging|prod)\.company\.com'
  severity: medium
  message: "Hardcoded environment URL"
  recommendation: "Use env var for base URL"
```

Test: `grep -E 'pattern' path/to/file`

Suggestions:
- Deprecated test utilities
- Missing data-testid
- Snapshot tests without descriptions
