# Manager Tasks Instance — Team Context

OpenCode-native counterpart to `CLAUDE.md`; keep both aligned during rollback.

## Team

- **Name**: HCC Framework
- **Manager**: Karel Hala (khala@redhat.com)

## Weekly Status Report

- **Repo**: `weekly-status` (from `project-repos.json`)
- **Scope**: `hcc-team all` (all HCC sub-teams)
- **Schedule**: Monday generate+PR, Tuesday 1pm Prague auto-merge
- **Merge policy**: auto-merge Tuesday 1pm Prague unless `CHANGES_REQUESTED` review exists

## Environment Constraints

- Non-interactive: never ask the user; use preflight parameters for target week,
  branch, and report type.
- Pre-commit: if `uvx`/`npx` unavailable, try `markdownlint`; if that also fails,
  skip local lint because CI validates the PR.
- Follow the active workflow's `AGENTS.md` for the complete task lifecycle.
