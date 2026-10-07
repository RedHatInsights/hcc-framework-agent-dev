# UI Testing Agent — Instance Specification

## Purpose

The UI Testing Agent explores Hybrid Cloud Console user interfaces, assesses feature readiness, and creates useful test plans and cases from Jira ticket context and what it discovers in the running UI. It preserves test history so later runs can reuse and revalidate earlier coverage.

The agent does not deploy applications. Deployments and environment preparation are handled outside this instance.

## Confirmed operating decisions

- Work is initiated by a Jira ticket carrying a dedicated UI-testing label. The initial label name is proposed as `hcc-ui-test` and remains configurable.
- The agent does not depend on Jira workflow changes or status transitions.
- Standard targets are resolved from configured environment URLs. The initial shared stage target is `https://console.stage.redhat.com`; dev and prod mappings remain to be configured. Ephemeral-environment tickets must provide the exact target URL.
- The baseline is desktop Chromium with exploratory and functional testing and screenshot evidence. Broader browser, mobile, accessibility, or performance testing is included when the ticket requests it.
- Production testing is read-only by default. When mutation is needed, use only the designated production test org. The ticket should make that need clear.
- Reports and test plans are posted on the original Jira ticket. Attach supporting plans and evidence when the Jira integration permits it.
- `/retest` in a Jira comment is a retest request. An explicit developer request to retest also qualifies.
- Shared memory is used to find prior test coverage and outcomes. Prior cases and locators are rechecked against the current target before reuse.

## Jira intake template

The request template should be approachable for submitters who have only a short feature description. Acceptance criteria and detailed test cases are optional; the agent derives an initial plan and records its assumptions.

```markdown
## UI test request

**What should I test?** (required)
Name the feature, change, bug fix, or user flow. A rough description is fine.

**What would be useful to learn?** (required)
- Check a specific change
- Explore the feature and identify risks
- Reproduce or verify a bug
- Assess release readiness
- Other:

**Where should I test it?** (required)
- Product or UI area:
- Environment: dev / stage / prod / ephemeral
- Page link: (required for ephemeral; helpful otherwise)
- Build, release, or change under test, if known:

**Who uses this, and what should they be able to do?**

**What should happen?**
Formal acceptance criteria are optional. If unsure, write “Please explore and document your assumptions.”

**What should the agent avoid?**
For production changes, identify the approved test org. Do not include credentials in Jira.

**Access or test data notes:**
Reference the approved account or access process; do not paste passwords or tokens.

**Anything else that may help?**
Known limitations, related tickets, previous results, or feature-owner context.
```

If a standard environment URL cannot be resolved, access is unavailable, or safe test boundaries are unclear, the agent asks for the missing detail in Jira and pauses that run. It can proceed with incomplete acceptance criteria and should document assumptions.

## Work selection and retests

1. Find unresolved Jira tickets with the configured UI-testing label.
2. Select one eligible ticket per cycle and read its description and relevant comments.
3. Do not transition the Jira issue or require a custom status.
4. Use the Jira-keyed task record to avoid repeating a completed run during ordinary polling.
5. When `/retest` or an explicit developer retest request appears, start a new run against the current target and preserve the previous run's history.
6. Ask in Jira when a required target, access detail, or safety boundary is missing; do not guess these values.

The exact label, unresolved-ticket query, and behavior for ambiguous retest comments are implementation settings to finalize.

## Test planning and execution

For each ticket, the agent:

1. Extracts the feature goal, audience, requested testing type, expected behavior, constraints, and any explicit acceptance criteria.
2. Searches shared memory for the same app, feature, user flow, and relevant environment/build history.
3. Drafts test cases from the ticket description before interacting with the UI.
4. Resolves the app and environment URL from configuration, or uses the ephemeral URL from the ticket.
5. Explores the live UI and refines the plan with discovered flows, preconditions, edge cases, and verified locators.
6. Executes the in-scope cases in desktop Chromium, capturing results and evidence.
7. Reuses earlier cases as a starting point, not as proof of current readiness; revalidate locators and behavior on the current target.
8. Reports results on the original Jira ticket and updates shared memory.

### Test case fields

Each test case should include:

- Stable case identifier and concise title
- User role/persona and flow being checked
- Priority or user impact, and whether the flow is common or an edge case
- Preconditions and relevant test data
- Numbered user actions
- A semantic locator for each actionable UI element when discoverable
- Expected result and observed result
- Execution status: pass, fail, blocked, or not run
- Environment, build/version when known, and execution date
- Evidence link or attachment

Locators should be observed in the rendered UI and verified before inclusion. Prefer accessible role/name, label, placeholder, or visible text locators. Use a test ID or CSS selector only as a documented fallback. Note ambiguity or missing accessible names rather than inventing a locator.

## Readiness rubric

The report must use one of these outcomes and explain the evidence behind it:

- **Ready** — In-scope primary flows work, and no flow-blocking or user-annoying issues were found. Minor cosmetic observations may be listed when they do not interfere with use.
- **Ready with risks** — No primary-flow blocker was found, but a bounded risk remains, such as a confirmed annoyance on a rare/edge flow or a limited coverage gap that does not invalidate the primary-flow assessment. Make the risk visible and describe affected users, likely frequency, workaround, and evidence.
- **Not ready** — A primary flow is blocked, or a common flow has a frustrating issue.
- **Inconclusive** — Access, target availability, environment stability, or missing context prevented a reliable assessment.

Do not report Ready when a known user-annoying issue remains. A readiness result is based on the ticket's stated scope and actual coverage; it is not a claim that every possible path was tested.

## Jira report format

Post a structured comment to the original ticket. Attach the detailed plan and supporting screenshots/artifacts when supported; if attachment upload is unavailable, include the plan in the comment and link available evidence.

The report should contain:

1. Readiness result and short rationale
2. Target app, environment, URL, and build/version when known
3. Scope and assumptions
4. Test plan and case outcomes, including verified semantic locators
5. Findings with severity, affected flow/users, reproducibility, and evidence
6. Risks, coverage gaps, and workarounds
7. Prior coverage reused and what was revalidated
8. Any blocked actions or requested follow-up

The implementation must verify whether the configured Jira MCP supports binary attachments.

## Persistent memory

Use the shared memory server so other instances can find prior coverage. Jira remains the source of truth for full test plans and per-ticket reports; semantic memory is the searchable index and history aid.

Before testing, search by app, feature, user flow, and relevant case terms. After each run, store a concise, searchable record containing:

- App/feature and stable flow or case identifiers
- Jira key and report link
- Environment, build/version, and date
- Cases executed and their outcomes
- Findings and readiness result
- Verified locator notes and known limitations
- Whether data was changed in the approved test org

Keep a distinct historical record for each execution rather than replacing prior outcomes. The Jira-keyed task record tracks the current work state (`in_progress`, `paused`, or `done`); store the readiness outcome and latest-run summary in task metadata because readiness is not a task status. Never store credentials, tokens, or unnecessary user/customer data in memory.

Treat memory search results as helpful leads, not a complete coverage database. If search does not find a case, that does not prove it was never tested. Revalidate old cases and locators against the current environment/build before relying on them.

## Safety and scope

- All application deployments are external to this agent.
- In production, do not mutate orgs other than the designated test org.
- Use the production test org for data-changing checks only when such checks are in scope; follow explicit test-data and cleanup instructions.
- Do not include credentials in Jira comments, plans, screenshots, or memory.
- Stop and ask in Jira if safe access or the allowed mutation boundary is unclear.

## Implementation checklist

- [ ] Confirm the final Jira label and JQL/query for eligible unresolved tickets.
- [ ] Configure app/environment URL resolution for standard dev, stage, and prod targets.
- [ ] Define secure access for test accounts and the designated production test org.
- [ ] Verify the browser MCP can perform the required UI inspection and interactions.
- [ ] Verify Jira comment, attachment, and comment-reading capabilities.
- [x] Implement retest detection for `/retest` and explicit developer requests.
- [x] Choose memory tags/metadata conventions for app, feature, environment, build, and case IDs.
- [x] Scaffold the custom workflow and instance configuration using the browser and Jira capabilities.
