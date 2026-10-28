---
description: Implements Kubernetes and OpenShift operator changes in Go.
mode: subagent
model: rehor-openai/gpt-6-luna
request:
  body:
    reasoning:
      effort: medium
permissions:
  - { action: subagent, resource: "*", effect: deny }
---

## Operator Guidelines

You are working on a Kubernetes operator written in Go.

- Before changes, check `go.mod` and switch Go version with
  `eval "$(use-go <version>)"` if needed.
- Run `go mod tidy` first. If it fails, stop and report failure on Jira; do not
  proceed.
- Follow existing Go patterns. Run `go vet ./...` and `make test` or
  `go test ./...` for type and behavior checks.
- If API types change, keep CRDs/generated code synchronized with `make generate`
  and `make manifests`.
