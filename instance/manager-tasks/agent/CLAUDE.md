# Manager Tasks Instance — Team Context

## Team

- **Name**: HCC Framework
- **Manager**: Karel Hala (khala@redhat.com)

## Weekly Status Report

- **Repo**: `RedHatInsights/weekly-status`
- **Scope**: `hcc-team all` (generate reports for all HCC sub-teams)
- **Schedule**: Tuesday generate + PR, Wednesday auto-merge
- **Merge policy**: auto-merge on Wednesday unless any GitHub review has `CHANGES_REQUESTED` status

## Environment Constraints

This instance runs in a Kubernetes pod without VPN access.

- **Skip VPN/LDAP checks**: The `ldapsearch` command is not available. When the weekly-status skill checks for LDAP connectivity, it will skip gracefully (Windows/missing-binary fallback path). Rover profile links will be omitted from reports — this is acceptable.
- **Non-interactive mode**: Never use `AskUserQuestion` or prompt for confirmation. All task parameters are provided by the preflight dispatch. When the weekly-status workflow would normally ask for confirmation (target week, branch creation, report type), proceed with the values from the preflight data.
- **Pre-commit**: If `uvx` or `npx` is not available for pre-commit hooks, run `markdownlint` directly on generated files instead. If that also fails, skip validation — CI on the PR will catch formatting issues.
