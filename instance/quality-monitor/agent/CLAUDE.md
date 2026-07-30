# Quality Monitor Instance - Team-Specific Context

This file supplements the workflow CLAUDE.md with instance-specific configuration.

## Team Context

- **Slack channel for alerts**: #platform-quality (update to your channel)
- **High-priority repos**: insights-chrome, rbac-service, platform-ui (update to your repos)
- **Escalation contact**: @platform-lead (update to your team lead)
- **Team timezone**: America/New_York
- **Business hours**: 9 AM - 5 PM ET

## Anti-Pattern Configuration

This instance uses `anti-patterns.yaml` for pattern definitions. See that file for:
- Detection regexes
- Severity levels
- Remediation guidance
- Code examples

When analyzing findings, reference the specific remediation templates from `anti-patterns.yaml` in your notifications.

## Notification Preferences

### Slack Notifications

**When to notify:**
- All merge violations (any severity)
- 5+ HIGH severity test anti-patterns
- Repeat offenders (3+ violations in 30 days)

**Format:**
- Short summary with severity
- Direct link to GitHub issue
- Tag relevant team (from CODEOWNERS)

### GitHub Issues

**When to create:**
- FAILURE conclusions in merge violations
- 3+ HIGH severity test anti-patterns
- Repeat offender repos

**Labels to apply:**
- `quality` (always)
- `ci-failure` (for merge violations)
- `tech-debt` (for anti-patterns)
- `testing` (for test-related issues)

**Assignment:**
- Don't auto-assign to individuals
- Tag team from CODEOWNERS in issue body
- Let team self-assign

## Repository-Specific Rules

### High-Priority Repos

For repos marked as high-priority above:
- Create GitHub issues for any severity (not just HIGH)
- Send Slack notifications for all findings
- Tag escalation contact for HIGH severity

### Known Exceptions

Some patterns may be intentional:
- `console.log` in debugging utilities (not in tests themselves)
- `.only()` in development branches (should never merge to main)
- Hardcoded test credentials in fixture files (if sanitized)

When in doubt, create the issue and let the team decide.

## False Positive Handling

If a team marks an issue as "won't fix" or "false positive":
1. Add note to memory with repo + pattern + reason
2. Don't create duplicate issues for same pattern in that repo
3. Still track in memory for trending
4. Re-evaluate quarterly (patterns may become relevant later)

## Remediation Tracking

Track in memory:
- When issues are created
- When team responds (comments, closes, labels)
- Time-to-remediation for HIGH severity
- Repeat offender patterns

Use memory to identify:
- Which repos/teams need more testing education
- Which anti-patterns are most common
- Whether remediation efforts are effective

## Schedule

This instance runs daily at 9 AM ET via KEDA cron scaling.

Each scan processes:
- All repos for merge violations (last 24 hours)
- Up to 10 repos for anti-pattern scanning (rotates daily)

Full anti-pattern coverage across all repos: ~1 week if you have 50+ repos.

## Custom Anti-Patterns

To add team-specific anti-patterns:
1. Edit `anti-patterns.yaml` in this workflow directory
2. Add new pattern with regex, severity, recommendation
3. Preflight script will automatically detect it
4. Test regex with: `grep -E 'your-pattern' path/to/test/file`

Example additions your team might want:
- Hardcoded environment URLs (staging/prod)
- Use of deprecated testing utilities
- Missing data-testid attributes (for E2E tests)
- Snapshot tests without descriptions

## Resources

Link to team documentation:
- Testing best practices: (add your wiki link)
- CI/CD troubleshooting: (add your runbook link)
- How to fix flaky tests: (add your guide link)
