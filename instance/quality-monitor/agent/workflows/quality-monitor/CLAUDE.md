# Quality Monitoring Workflow

Automated code quality monitoring for repository health checks.

## Overview

This workflow runs on a scheduled basis to detect quality issues:
1. **Merge violations** - PRs merged with failed CI checks
2. **Test anti-patterns** - Hard-coded sleeps, disabled tests, missing assertions

## Cycle Loop

ONE finding per cycle (highest priority first).

### Priority Order

1. **P0**: Handle feedback on existing quality tasks (GitHub issue comments, Slack replies)
2. **P1**: Merge violations (FAILURE > CANCELLED > SKIPPED)
3. **P2**: High-severity test anti-patterns
4. **P3**: Medium/low-severity test anti-patterns

### Input Data

Preflight scripts provide findings. No re-fetch during session.

## P0: Handle Feedback

Check existing quality tasks for:
- GitHub issue comments requesting action
- Slack thread replies
- Task status updates needed

ONE feedback item per cycle.

## P1: Process Merge Violations

When preflight `01-check-merged-prs.py` returns violations:

### Decision Flow

1. **Read preflight data** with merge violations
2. **Select highest priority violation**:
   - FAILURE conclusions first (actual test/build failures)
   - CANCELLED second (interrupted builds)
   - SKIPPED third (potentially intentional)
3. **Analyze impact**:
   - Which checks failed and why
   - Assess risk level (critical path vs optional checks)
   - Check if repeat offender (query memory for patterns)
4. **Create notifications**:
   - Create GitHub issue for FAILURE conclusions
   - Send Slack notification for all violation types
   - Tag appropriate team from CODEOWNERS
5. **Track in memory**:
   - Create task with `source_type: "github"`
   - External key: `merge-violation:{repo}:{pr_number}`
   - Metadata includes PR details and failed checks

### GitHub Issue Template

For FAILURE conclusions only:

```markdown
## PR Merged with Failed Checks

**PR:** #{pr_number} - {pr_title}
**Merged:** {timestamp}
**Author:** @{author}

### Failed Checks

{for each check}
- [ ] **{check.name}** - {check.conclusion}
  - Details: {check.url}
{endfor}

### Action Items

- [ ] Review merged code for potential issues
- [ ] Determine why checks failed
- [ ] Fix underlying issue or revert if needed
- [ ] Update CI configuration if appropriate

### Context

This PR was merged despite having failed checks. This may indicate:
- Urgent hotfix that bypassed normal process
- Flaky test that was incorrectly ignored
- CI configuration issue that needs attention

/cc @{team-from-codeowners}
```

Labels: `quality`, `ci-failure`, `needs-investigation`

### Slack Notification Template

```
⚠️ **PR Merged with Failed Checks**

*Repository:* {repo}
*PR:* <{pr_url}|#{pr_number} - {pr_title}>
*Author:* @{author}
*Merged:* {timestamp}

*Failed Checks:*
{for check in failed_checks}
• `{check.name}`: {check.conclusion}
  {check.url if available}
{endfor}

*Recommended Actions:*
1. Review the merged changes for potential issues
2. Investigate why checks were bypassed or failed
3. Consider reverting if critical functionality affected

*Severity:* {HIGH/MEDIUM/LOW}
```

## P2/P3: Process Test Anti-Patterns

When preflight `02-scan-test-anti-patterns.py` returns test files to analyze:

### Decision Flow

1. **Read preflight data** - it lists test files to analyze
2. **Read `anti-patterns.yaml`** from the workflow directory - this contains:
   - Pattern definitions with human-readable descriptions
   - Code examples (bad vs good)
   - Severity levels and remediation guidance
3. **Read sample test files** from the listed repositories
4. **Analyze for anti-patterns** using the definitions from anti-patterns.yaml:
   - Look for patterns matching the examples
   - Focus on HIGH severity first (hard-coded sleeps, missing assertions)
   - Note specific file:line locations
5. **Select repository** with most HIGH severity issues found
6. **Analyze findings**:
   - Group related anti-patterns (e.g., all sleeps in same test suite)
   - Identify systemic issues vs one-offs
   - Check memory for previous scans of this repo
4. **Create remediation plan**:
   - Specific file:line fixes needed
   - Recommended refactoring approach
   - Estimated effort/priority
5. **Notify team**:
   - Create GitHub issue in the repository
   - Send Slack notification if 5+ HIGH severity
6. **Track in memory**:
   - Create task with `source_type: "github"`
   - External key: `test-scan:{repo}`
   - Metadata includes finding counts and patterns

### GitHub Issue Template

```markdown
## Test Quality: {pattern_count} Anti-Patterns Detected

Automated scan found {pattern_count} test anti-patterns in this repository.

### High Severity Issues ({high_count})

{for each high severity finding}
#### {finding.message}

**Location:** `{finding.file}:{finding.line}`
**Code:**
\`\`\`
{finding.snippet}
\`\`\`

**Recommendation:** {finding.recommendation}

---

{endfor}

### Medium Severity Issues ({medium_count})

<details>
<summary>Click to expand</summary>

{for each medium finding}
- `{finding.file}:{finding.line}` - {finding.message}
{endfor}

</details>

### Remediation Priority

1. Address all HIGH severity issues first (hard-coded sleeps, missing assertions)
2. Create tech debt tickets for MEDIUM issues (disabled tests)
3. LOW issues can be addressed opportunistically

### Resources

- [Testing Best Practices](https://github.com/goldbergyoni/javascript-testing-best-practices)
- [Effective Wait Strategies](https://www.selenium.dev/documentation/webdriver/waits/)

---

**Labels:** `quality`, `tech-debt`, `testing`

**Auto-generated by Rehor Quality Monitor**
```

### Slack Notification

For repositories with 5+ HIGH severity issues:

```
🧪 **Test Quality Alert**

*Repository:* {repo}
*Scan Date:* {date}

*Findings:*
• {high_count} HIGH severity anti-patterns
• {medium_count} MEDIUM severity issues

*Top Issues:*
{top 3 patterns with counts}

*Action Required:*
Created GitHub issue: {issue_url}

Please review and prioritize remediation.
```

## Task Tracking

### Merge Violations

```python
task_add(
    external_key=f"merge-violation:{repo}:{pr_number}",
    source_type="github",
    repo=repo,
    status="in_progress",
    title=f"Investigate PR #{pr_number} merged with failed checks",
    metadata={
        "pr_number": pr_number,
        "pr_url": pr_url,
        "pr_title": pr_title,
        "author": author,
        "failed_checks": [...],
        "severity": "high|medium|low",
        "issue_url": github_issue_url
    }
)
```

Mark complete when:
- Issue created and team notified
- Investigation tracked in GitHub issue
- Follow-up scheduled if HIGH severity

### Test Anti-Patterns

```python
task_add(
    external_key=f"test-scan:{repo}",
    source_type="github",
    repo=repo,
    status="in_progress",
    title=f"Address {finding_count} test anti-patterns in {repo}",
    metadata={
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
        "patterns_found": pattern_names,
        "issue_url": github_issue_url,
        "scan_date": date
    }
)
```

Mark complete when:
- Issue created and team notified
- Remediation tracked in GitHub issue
- Follow-up scan scheduled

## Memory Storage

After handling each finding:

```python
memory_store(
    category="learning",
    tags=["quality", "ci-violations" or "testing", repo],
    content=f"""
Quality scan of {repo} on {date}:
Type: {merge-violation or test-anti-patterns}
Findings: {summary}
Pattern suggests: {analysis}
Recommended approach: {recommendation}
Outcome: {what_was_done}
"""
)
```

Track patterns over time:
- Repeat offenders (same repo/team with violations)
- Common anti-patterns across repos
- Remediation effectiveness
- Team response times

## Rules

- **ONE finding per cycle** - don't spam teams with bulk notifications
- **Prioritize HIGH severity** - FAILURE conclusions and hard-coded sleeps first
- **Always include direct links** - PR URLs, issue URLs, file:line references
- **Tag appropriate teams** - use CODEOWNERS, not @everyone
- **Track repeat offenders** - escalate if patterns emerge
- **Update task status** - mark complete when addressed or delegated
- **Be constructive** - suggest fixes, not just problems
- **Learn from patterns** - save insights to memory for trending

## Notification Guidelines

### When to Create GitHub Issues

- ✅ FAILURE conclusions in merge violations
- ✅ 3+ HIGH severity test anti-patterns
- ❌ Single SKIPPED check (just Slack)
- ❌ <3 total anti-patterns (too noisy)

### When to Send Slack Notifications

- ✅ All merge violations (any severity)
- ✅ 5+ HIGH severity test anti-patterns
- ✅ Repeat offenders (3+ violations in 30 days)
- ❌ Single low-severity finding

### Notification Batching

Don't create separate notifications for related findings:
- Group all anti-patterns from same repo into one issue
- Batch multiple SKIPPED checks from same PR into one Slack message
- Daily digest format if 10+ findings in one scan

## Error Handling

If unable to create notification:
1. Log error to memory
2. Create fallback task for manual follow-up
3. Continue to next finding (don't block on one failure)

If GitHub API rate limited:
1. Wait and retry once
2. If still failing, save findings to memory
3. Process in next cycle

## Capacity Management

Respect the 10-task limit:
- Query `get_capacity()` before creating tasks
- If at capacity, log findings to memory
- Process in next cycle when capacity available
- Don't drop findings silently

## Success Metrics

Track in memory:
- Violations detected per day
- Team response time to notifications
- Remediation rate (issues closed)
- Repeat offender trends
- False positive rate
