# HCC Framework Instance — Additional Instructions

## Version Management

This instance has **nvm** (Node) and **goenv** (Go) version managers installed. Use them to match the version required by each repo.

### Node.js (nvm)

Before working on a repo with `package.json`, check its `.nvmrc` or `engines.node` field and switch if needed:

```bash
nvm use          # reads .nvmrc if present
nvm install 20   # install + switch to Node 20
nvm use default  # back to default (22)
```

Default: Node.js 22 LTS. Available globally via `/usr/local/bin/node`.

### Go (goenv)

Before working on a repo with `go.mod`, check the `go` directive and switch if needed:

```bash
goenv versions                    # list installed versions
goenv install 1.23.0              # install a new version
goenv global 1.23.0               # set as default
goenv local 1.24.2                # set for current directory only
```

Pre-installed: Go 1.24.2 (default), 1.25.7. Available globally via `/usr/local/bin/go`.

### When to switch

- `go.mod` says `go 1.23` → `goenv install 1.23.x && goenv local 1.23.x`
- `.nvmrc` says `20` → `nvm use 20` (installs automatically if missing)
- No version file → use the defaults

## Node.js

Do no run tasks like lint, build, tests and others in paraller, they are memory intensive and can kill your env. Run then in sequence.
Even things like jest, try to run them in band to reduce the memory usage.

## Visual verification and PR publication

For this Framework instance, the following exception overrides Jira Sprint's
“Skip = rejection” rule for visual verification only. It applies to both new
and existing PRs.

- Attempt visual verification for UI changes. If the environment blocks it
  (for example, missing proxy runtime, browser, or Console access), or a
  verified maintainer takes over manual verification, run the available checks
  and proceed with the normal push to `bot/<TICKET-KEY>`. Do not hold the push
  solely for the missing visual check.
- In the PR description or a review reply, state what passed, what remains
  unverified, and how to verify it manually. Record any maintainer handoff.
  An isolated preview is not proof of a full Console render.
- Do not mark a known regression ready for merge. All other verification and
  push restrictions still apply.

## Konflux tenant onboarding and migration

When onboarding a component to Konflux or migrating it between tenants or
clusters, use the profile's `.opencode/skills/konflux-migration/SKILL.md`.
