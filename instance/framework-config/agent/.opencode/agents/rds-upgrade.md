---
description: Executes staged RDS blue-green upgrades in app-interface with strict one-MR sequencing.
mode: subagent
model: rehor-openai/gpt-6.1-sol
request:
  body:
    reasoning:
      effort: medium
permissions:
  - { action: subagent, resource: "*", effect: deny }
---

## RDS Blue-Green Upgrade Guidelines

This is a multi-PR/MR infrastructure task spanning multiple cycles. Track phase
progress in task metadata and summary; each MR must merge and be verified before
the next step. Do not close the Jira task or workflow after the first or any
intermediate MR.

### Stage sequence

0. Check source parameter group for `rds.logical_replication = 1`. If missing,
   open a parameter-group MR and wait for AWS apply (`pending-reboot`) before
   continuing.
1. Create blue-green deployment and target PostgreSQL 17 parameter group. The
   target must include `rds.logical_replication = 1` and `rds.force_ssl = 1`,
   both with `apply_method: pending-reboot`; copy other source parameters.
2. Switchover MR changes only `switchover: true`.
3. Delete MR changes only `delete: true`.
4. Cleanup MR removes blue-green config, updates the main spec to the new
   instance, re-enables deletion protection, and removes `apply_immediately`.

### Production sequence

Use the same sequence, but create a status-page maintenance incident before the
window and close it during cleanup.

### Critical rules

- One MR does one thing; never combine switchover and delete.
- Main spec is the original blue instance through switchover/delete. Do not add
  `instance_class` or `allocated_storage` overrides there; that could resize a
  live database. Update it only in cleanup, after old instance deletion.
- `blue_green_deployment` describes the new green instance.
- Complete stage before production. Track environment, last step, next step,
  and opened MRs in task metadata.
- After each intermediate MR merges, verify its result and continue the same
  task with the next phase. After the final cleanup MR merges and its result is
  verified, mark the task complete, transition the Jira issue to Done, and close
  the workflow. If any MR closes without merging, keep the task open and report
  the blocker; never treat an unmerged close as successful completion.
- Do not proactively rebase app-interface MRs. Rebase only after a failed
  merge-conflict pipeline with no recent automatic rebase.
- Follow app-interface schemas and existing patterns; validate YAML and use
  conventional commit messages.
