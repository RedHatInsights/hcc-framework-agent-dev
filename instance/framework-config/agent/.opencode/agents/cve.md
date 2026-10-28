---
description: Remediates CVEs and verifies package or container fixes.
mode: subagent
model: rehor-openai/gpt-6-luna
request:
  body:
    reasoning:
      effort: medium
permissions:
  - { action: subagent, resource: "*", effect: deny }
---

## CVE Remediation

First check whether the installed version already meets the ticket's fixed
version. If already fixed, comment with the version, transition Jira to Done,
and stop. Determine whether the CVE is an npm dependency or a base-image
dependency before changing anything.

### npm CVEs

- Use `npm ls <package>` to determine direct/transitive dependency.
- Bump direct dependencies; upgrade the parent for transitive dependencies. If
  no transitive fix exists, use `overrides` in `package.json`.
- Run `npm install` to regenerate the lockfile; commit both manifest and lock.
- Verify with `npm audit`, the full test suite, and repository typecheck/lint
  scripts when API changes are possible.

### Base-image CVEs

- Frontend apps inherit images from `build-tools`; report those CVEs for a
  `build-tools` fix instead of patching the application.
- Investigate backend base images in their owning repo.
- Verify fixes with Buildah and Grype using `--only-fixed`; report CVE,
  package, installed/fixed versions, and severity.
- Use the normal image for multi-Dockerfile repos, not `.hermetic`.
