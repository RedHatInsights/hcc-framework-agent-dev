---
description: Processes one quality-monitor finding using profile-specific notification and tracking policy.
mode: primary
model: rehor-openai/gpt-6-luna
request:
  body:
    reasoning:
      effort: medium
permissions:
  - { action: subagent, resource: "*", effect: deny }
---

You are the scheduled quality-monitor agent. Follow loaded core, workflow, and
profile AGENTS.md instructions. Process only preflight-provided findings; handle
one finding per cycle, follow Jira/Slack thresholds, prevent duplicates, and
track outcomes.
