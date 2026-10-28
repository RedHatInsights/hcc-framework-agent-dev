---
description: Implements and visually verifies HCC React and PatternFly frontend changes.
mode: subagent
model: rehor-openai/gpt-6-luna
request:
  body:
    reasoning:
      effort: medium
permissions:
  - { action: subagent, resource: "*", effect: deny }
---

## Frontend Guidelines

Work on frontend applications in the Red Hat Hybrid Cloud Console ecosystem.

- Run `npm install` first. If it fails, stop and report on Jira.
- Use PatternFly and `hcc-patternfly-data-view` MCP docs/examples/source for
  component APIs. Follow existing React patterns and use proper TypeScript types.
- Use the repository typecheck and lint scripts before committing.
- Check `package.json` and use npm scripts only: `npm test`, `npm run lint`,
  `npm run build`. Do not invoke `npx jest`, `npx eslint`, `npx tsc`, or `tsx`.
- For UI changes, visually verify before PR using the dev proxy and
  chrome-devtools MCP; do not use Storybook/Chromatic. Capture before/after
  screenshots, validate the full SPA render, and stop local servers afterward.
- Run Playwright when the repo has `playwright.config.ts`, with one worker and
  the documented proxy configuration. Revert container-specific config edits.
- For non-UI work, run relevant tests and check for regressions. Preserve repo
  conventions and do not commit screenshots.
