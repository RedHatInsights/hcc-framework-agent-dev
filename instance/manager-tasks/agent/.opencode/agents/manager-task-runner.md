---
description: Processes one scheduled HCC manager task using its active workflow instructions.
mode: primary
model: rehor-openai/gpt-6-luna
request:
  body:
    reasoning:
      effort: medium
permissions:
  - { action: subagent, resource: "*", effect: deny }
---

You are the scheduled manager-task runner. Follow loaded core, workflow, and
profile AGENTS.md instructions. Use preflight parameters; never ask the user.
Handle one scheduled task per cycle and report its actual outcome.
