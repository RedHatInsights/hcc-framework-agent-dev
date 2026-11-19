# Quality Monitoring Workflow

OpenCode-native instructions for this custom workflow. Legacy `CLAUDE.md` stays
for Python/Claude rollback; this file contains active OpenCode workflow rules.

## Cycle policy

- Process one finding or feedback item per cycle, highest priority first.
- Use preflight findings as authoritative; do not re-fetch their source data.
- Priority: P0 feedback on existing quality tasks; P1 merged PRs with failed
  CI; P2 high-severity test anti-patterns; P3 medium/low anti-patterns.
- For P0, handle one Jira comment, Slack reply, or task-status update; transition
  tickets from In Progress to Done only when work is complete.
- For Jira feedback, resume the task named by the preflight rather than creating
  a new task. After addressing the feedback, update `last_addressed` and the
  task summary; keep it active while further Jira feedback is expected.

## Merge violations

- Process FAILURE conclusions only as Jira violations; CANCELLED and SKIPPED
  are tolerated. Notify Slack for all merge violations.
- Before creating work, query memory for `merge-violation:{repo}:{pr_number}`;
  skip if already tracked. Assess failed checks, risk, repeat-offender history,
  and CODEOWNERS team.
- Create an RHCLOUD Bug with High priority and labels `quality`, `ci-failure`,
  `needs-investigation`. Include PR/repo/merge/author details, failed checks,
  action items, and direct links. Notify the team in Slack and tag the owner.
- Track a task with `source_type: jira`, external key
  `merge-violation:{repo}:{pr_number}`, `instance_id` set to the value of
  `BOT_INSTANCE_ID`, `repo`, `status: in_progress`, and `metadata.jira_key` set
  to the created ticket key. Include ticket/PR metadata, failed checks, severity,
  and creation time. Keep it active until work is done.

## Test anti-patterns

- Use the preflight-listed test files and workflow `anti-patterns.yaml`; inspect
  code context and prioritize hard-coded sleeps, missing assertions, and swallowed
  errors. Do not scan unrelated repositories.
- Check task memory for `test-scan:{repo}:{scan_date}` before creating tickets.
- Create an RHCLOUD Task only for 3+ HIGH findings. Priority is Medium for 3–5
  HIGH and High for 6+. Apply labels `quality`, `tech-debt`, `testing`,
  `anti-patterns`; group a repo's related findings into one ticket.
- Send Slack notification for 5+ HIGH findings and repeat offenders (3+ in
  30 days). Include repo, scan date, counts, top patterns, and ticket link.
- Track ticketed findings with `source_type: jira`, `status: in_progress`,
  `instance_id` set to the value of `BOT_INSTANCE_ID`, `repo`, scan date, counts,
  and `metadata.jira_key` set to the ticket key.
- For HyperShell preflight results, once analysis of a repo is complete, record
  its supplied Task ID as the external key. If no ticket is needed, create a
  `source_type: manual`, `status: done` task with that key, instance ID, repo,
  scan date and counts. Do not create the scan marker before analysis finishes.
  Leave other repos untracked until their own analysis is complete.

## Completion and errors

- Query task memory before creating duplicate Jira tickets. Respect the 10-task
  capacity; if full, log findings to memory and process later.
- If notifications fail, record the error and create a follow-up task; do not
  silently drop findings. If GitHub rate-limits, wait and retry once, then save
  findings for a later cycle.
- Keep direct PR/ticket/file-line links. Be constructive and suggest fixes.
- Track detection volume, response/remediation time, repeated patterns, and
  false positives. A team `won't fix` decision should be remembered and skipped
  for duplicate scans, then re-evaluated quarterly.
