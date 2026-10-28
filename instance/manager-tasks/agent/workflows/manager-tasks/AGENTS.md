# Manager Tasks Workflow

OpenCode-native instructions for this custom workflow. Legacy `CLAUDE.md` stays
for Python/Claude rollback; this file contains active OpenCode workflow rules.

## Dispatch and tracking

- Preflight selects one task through its `TASK:` header. Never ask the user;
  use preflight values for week, branch, and report type.
- Stable task ID: `{task-name}-{YYYY-MM-DD}` across generate, feedback, and merge.
- `task_status: new`: create task with that ID as `external_key` and
  `source_type: scheduled`. `in_progress`: continue existing task. End each
  cycle with `task_update` including status, summary, and metadata.
- All report scripts, prompts, and context live in `hp-weekly-status` from
  `project-repos.json`; do not recreate them in the bot repo.

## `weekly-report-generate`

1. Enter `hp-weekly-status`, fetch upstream, and check out upstream main.
2. Run `.claude/skills/weekly-status/scripts/detect_week.py`; use returned
   Friday, week directory, and git username to create
   `{git_user}/hcc-team-weekly-report-{friday}`.
3. Read team context, `prompts/team-report.md`, `STYLE_GUIDE.md`, and prior
   week's report. Collect Jira issues for Thursday–Wednesday using paginated
   `jira_search`; collect GitHub data with `collectors/collect_github.py` for
   repos from context.
4. Generate each team report in the specified week directory. Then run
   `combine_reports.py` for the combined view.
5. Validate generated files with pre-commit. If unavailable, try markdownlint;
   if unavailable too, skip and rely on CI.
6. Commit only the generated week directory, push, open the report PR, then
   notify Slack with its URL. Follow the report's configured Tuesday 1pm Prague
   auto-merge policy unless a `CHANGES_REQUESTED` review exists.

## `weekly-report-feedback`

- Use the feedback already supplied in the cycle prompt; do not re-fetch GitHub
  review comments.
- Check out the specified PR branch in `hp-weekly-status`, fix each requested
  report change, commit, and push. Reply to the corresponding review comments.

## `weekly-report-merge`

- Inspect PR review decision. Do not merge when review decision is
  `CHANGES_REQUESTED`; report the blocker in Slack. Otherwise squash-merge and
  delete the branch, then notify Slack.

`jira-cleanup` remains a placeholder with no automated action. Never handle
multiple scheduled tasks in one cycle.
