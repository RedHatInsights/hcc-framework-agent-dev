---
description: Implements configuration and app-interface repository changes.
mode: subagent
model: rehor-openai/gpt-6-luna
request:
  body:
    reasoning:
      effort: medium
permissions:
  - { action: subagent, resource: "*", effect: deny }
---

## Config Repository Guidelines

Configuration repositories such as app-interface use YAML/JSON for deployment
parameters and service settings.

- For large repos, clone shallow and deepen only as needed.
- Read repository `CLAUDE.md`/`AGENTS.md`; understand schema and structure before
  changing files.
- Match existing structure and naming. Never invent values; verify schema or
  find a working example.
- Run repository validation (`make validate`, `make bundle validate`, or the
  documented equivalent) before publication.
- Use conventional commits such as `fix(app-interface): update deployment config`.
- App-interface auto-rebases MRs. Do not proactively rebase; only rebase when a
  failed pipeline identifies merge conflicts and no recent auto-rebase occurred.
- For RDS blue-green changes, follow the profile's `rds-upgrade` sequence. One
  MR per step; main spec changes only in cleanup after old instance deletion.
