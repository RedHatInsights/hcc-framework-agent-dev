---
description: Implements shared build, container, proxy, shell, and CI tooling changes.
mode: subagent
model: rehor-openai/gpt-6-luna
request:
  body:
    reasoning:
      effort: medium
permissions:
  - { action: subagent, resource: "*", effect: deny }
---

## Tooling and Build Infrastructure Guidelines

These repositories contain shared infrastructure with broad blast radius.
Prioritize stability and follow existing patterns. Read the repo README/docs.

- Dockerfiles: prefer minimal multi-stage UBI builds, pin base images, run
  non-root where possible, and never hardcode secrets.
- Shell: use `set -euo pipefail`, quote variables, comment non-obvious logic,
  and run ShellCheck when available.
- Proxy/Caddy/NGINX: respect route ordering and test against a running instance
  where possible; document new configuration.
- Go plugins: use gofmt, `go vet`, `go build`, and `go test ./...` as relevant.
- Validate config syntax and run repo test suites. Check Makefile/CI targets.
- CVEs are usually in base images/system packages; verify the fixed package
  version in the resulting image.
