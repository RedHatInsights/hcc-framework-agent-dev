# Manager Tasks Instance — Team Context

## Team

- **Name**: HCC Framework
- **Manager**: Karel Hala (khala@redhat.com)

## Weekly Status Report

- **Repo**: `RedHatInsights/weekly-status`
- **Scope**: `hcc-team all` (all HCC sub-teams)
- **Schedule**: Tuesday generate+PR, Wednesday auto-merge
- **Merge policy**: auto-merge Wednesday unless `CHANGES_REQUESTED` review exists

## Environment Constraints

- **Non-interactive**: Never use `AskUserQuestion`. All params from preflight. Proceed with preflight values for target week, branch, report type.
- **Pre-commit**: If `uvx`/`npx` unavailable, run `markdownlint` directly. If that fails too, skip — CI catches issues on PR.
