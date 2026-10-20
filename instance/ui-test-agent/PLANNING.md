# UI Testing Agent — Instance Specification

## Purpose

The UI Testing Agent explores Hybrid Cloud Console user interfaces, assesses feature readiness, and creates useful test plans and cases from Jira ticket context and what it discovers in the running UI. It preserves test history so later runs can reuse and revalidate earlier coverage.

The agent does not deploy applications. Deployments and environment preparation are handled outside this instance.

## Confirmed operating decisions

- Work is initiated by a Jira ticket carrying a dedicated UI-testing label. The initial label name is proposed as `hcc-ui-test` and remains configurable.
- The agent does not depend on Jira workflow changes or status transitions.
- Standard targets are resolved from configured environment URLs: dev `https://console.dev.redhat.com`, stage `https://console.stage.redhat.com`, and prod `https://console.redhat.com`. Ephemeral-environment tickets must provide the exact target URL.
- The local Stage harness routes Chromium through the corporate Squid proxy at `http://squid.corp.redhat.com:3128`; Stage model cycles have completed. The instance deployment template sets a browser-only proxy override to the existing `devbot-proxy`; deployed network reachability still needs validation. Do not replace the pod-wide proxy used by Jira, memory, and agent traffic.
- The baseline is desktop Chromium with exploratory and functional testing and screenshot evidence. Broader browser, mobile, accessibility, or performance testing is included when the ticket requests it.
- Production testing is read-only by default. When mutation is in scope, use the approved test-account credentials; the signed-in account determines its pre-existing test org, so no separate org ID is required. The ticket should make the need for mutation clear.
- Test identities are selected by a non-secret profile alias. Start with `org-admin` and `non-org-admin` for the two basic access contexts. Credentials remain in Vault-backed Kubernetes Secrets; a credential helper resolves the requested alias and performs login without returning secret values to the agent. Add more specific persona aliases as testing needs evolve, by adding secret references and profile metadata rather than per-user environment variables or helper code. The alias names describe intended access; the signed-in UI must still confirm the actual account, org, and role. The default alias and exact Vault/Secret naming convention remain to be set during deployment design.
- Reports and test plans are posted on the original Jira ticket. Attach supporting plans and evidence when the Jira integration permits it.
- `/retest` in a Jira comment is a retest request. New comments on a completed task are routed to the agent for semantic assessment; natural-language requests to retest qualify when the intent is clear.
- Shared memory is used to find prior test coverage and outcomes. Prior cases and locators are rechecked against the current target before reuse.

### Initial Stage profile mapping

The `hcc-platex-services-tenant` `chrome-credentials-secret` ExternalSecret in `konflux-release-data` provides a useful starting point:

- `org-admin` can map to the `username` and `password` keys, sourced from the insights-chrome E2E account. Treat its admin role as unverified until the Stage UI confirms it.
- `non-org-admin` can map to `E2E_NON_ADMIN_USER` and `E2E_NON_ADMIN_PASSWORD`.

The generated Secret belongs to the Konflux tenant namespace, so a runtime agent in another namespace cannot reference that Secret directly. Configure a dedicated Vault-backed Secret for the agent's namespace using the same source references; do not mount the broader `devbot-secrets` bundle into the login helper. The helper reads `<alias>.username` and `<alias>.password` files from its private credential mount, defaulting to `/var/run/ui-test-credentials`. Keep credential values and Vault paths out of agent config. Add personas by adding secret keys, not per-user environment variables or helper code.

### Deployment design note: credential helper

The reusable helper lives in `agent/login-helper`. The instance-specific OpenShift template deploys it as a sidecar in the bot's existing pod. Mount the dedicated profile Secret read-only into the helper only; do not expose those profile values in the bot container's environment or filesystem. The helper resolves `<alias>.username` and `<alias>.password` from `UI_TEST_CREDENTIALS_DIR` (default `/var/run/ui-test-credentials`), performs Stage SSO through the pod's existing Chromium CDP session, and exposes only the narrow `sign_in(alias)` MCP tool on pod loopback. A token-protected loopback control route resets the one-submission guard at each new work cycle; the runner removes its reset-token environment variable before starting model tools. The helper needs no separate Deployment, Service, or Route. The existing Konflux `chrome-credentials-secret` is in the Konflux tenant namespace, so provision an equivalent dedicated Vault-backed Secret in the agent namespace.

See [DEPLOYMENT.md](DEPLOYMENT.md) for the template, Secret key contract, and staged rollout checks.

## Jira intake template

The request template should be approachable for submitters who have only a short feature description. Acceptance criteria and detailed test cases are optional; the agent derives an initial plan and records its assumptions. The copy-ready version lives in [JIRA-REQUEST-TEMPLATE.md](JIRA-REQUEST-TEMPLATE.md).

If a standard environment URL cannot be resolved, access is unavailable, or safe test boundaries are unclear, the agent asks for the missing detail in Jira and pauses that run. It can proceed with incomplete acceptance criteria and should document assumptions.

## Work selection and retests

1. Find unresolved Jira tickets with the configured UI-testing label.
2. Select one eligible ticket per cycle and read its description and relevant comments.
3. Do not transition the Jira issue or require a custom status.
4. Use the Jira-keyed task record to avoid repeating a completed run during ordinary polling.
5. When a new comment appears after a completed run, assess whether it requests a retest. Start a new run only for `/retest` or a clear natural-language request, and preserve the previous run's history.
6. Ask in Jira when a required target, access detail, or safety boundary is missing; do not guess these values.

The implementation reads its dedicated label from `BOT_LABEL` and searches unresolved issues with that label. A standalone `/retest` is explicit; other new comments are sent to the agent for semantic assessment, with clarification requested when intent is ambiguous.

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

Keep exploration bounded so the full report is completed in the same cycle. For broad requests, inventory the relevant UI, exercise representative high-impact behavior, and write detailed cases for other discovered functionality as `not run` when it was not exercised. Do not try to execute every drafted case in one cycle. After two reasonable attempts to clarify an interaction, record the evidence and coverage gap and move on. If a turn-budget warning appears, stop browser exploration and spend the remaining turns reporting findings and updating memory.

### Test case fields

Each test case should include:

- Stable case identifier and concise title
- User role/persona and flow being checked
- Priority or user impact, and whether the flow is common or an edge case
- Preconditions and relevant test data
- A tester-ready, numbered sequence of atomic user actions, with enough detail to perform each action without guessing
- The relevant verified semantic locator or locators beside every step that interacts with a UI control, for later automation
- Expected result for each step when useful, plus an overall expected result and the observed result
- Execution status: pass, fail, blocked, or not run
- Environment, build/version when known, and execution date
- Evidence link or attachment

Write reports in readable Markdown, with one heading and structured details for each case. A summary table may be included, but it must not replace the full procedures. A numbered step describes one action and names the page/control, relevant input, and resulting state. Every step that interacts with a UI control must include that control's relevant, verified semantic locator or locators beside the action. If no semantic locator can be verified, state that explicitly and include an inspected test-ID or CSS fallback when available; never invent or silently omit a locator. Split broad summaries like “sign in, open the dashboard, and check the widgets” into the actual navigation, interaction, and verification steps. Include setup and cleanup when a case changes persistent or shared state; explain how to restore state when safe. Blocked and not-run cases still need the planned actions and expected results, plus the reason execution did not happen.

Carry relevant controls, states, and behaviors discovered during exploration into the test cases, even when the ticket did not mention them. Do not invent unobserved locators or behavior: label assumptions and unverified steps clearly, and record what needs confirmation. The report should let a tester who did not participate in exploration execute the case without having to infer missing actions.

Locators should be observed in the rendered UI and verified before inclusion. Prefer accessible role/name, label, placeholder, or visible text locators. Use a test ID or CSS selector only as a documented fallback. Note ambiguity or missing accessible names rather than inventing a locator.

## Readiness rubric

The report must use one of these outcomes and explain the evidence behind it:

- **Ready** — In-scope primary flows work, and no flow-blocking or user-annoying issues were found. Minor cosmetic observations may be listed when they do not interfere with use.
- **Ready with risks** — No primary-flow blocker was found, but a bounded risk remains, such as a confirmed annoyance on a rare/edge flow or a limited coverage gap that does not invalidate the primary-flow assessment. Make the risk visible and describe affected users, likely frequency, workaround, and evidence.
- **Not ready** — A primary flow is blocked, or a common flow has a frustrating issue.
- **Inconclusive** — Access, target availability, environment stability, or missing context prevented a reliable assessment.

Do not report Ready when a known user-annoying issue remains. A readiness result is based on the ticket's stated scope and actual coverage; it is not a claim that every possible path was tested.

## Jira report format

Post a structured comment to the original ticket. Include the complete tester-ready procedures in readable Markdown by default. Attach the detailed plan and supporting screenshots/artifacts when supported; if attachment upload is unavailable, include the full plan in the comment and link available evidence. A summary table is supplementary and must not stand in for test steps.

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
- In production, use the approved test-account credentials; the signed-in account determines its pre-existing test org.
- Keep production read-only unless data-changing checks are in scope. Before mutation, confirm the active account/org context; follow explicit test-data and cleanup instructions.
- Do not include credentials in Jira comments, plans, screenshots, or memory.
- Stop and ask in Jira if safe access or the allowed mutation boundary is unclear.

## Implementation checklist

- [x] Build contributor-ready local harness for fake Jira, memory, authentication, and one-cycle agent runs.
- [x] Package the copy-ready Jira intake template with the instance.
- [ ] Confirm the final Jira label and JQL/query for eligible unresolved tickets.
- [x] Configure shared URL resolution for standard dev, stage, and prod targets.
- [x] Add the narrow `stage-login.sign_in` tool to the framework allowlist and require its MCP server in the UI-test workflow.
- [x] Add an instance-specific deployment template for the helper sidecar, loopback health checks, and helper-only credential mount.
- [x] Reset the one-submission guard between work cycles without exposing a model-callable reset tool.
- [x] Add a paused Stage App Interface resource and namespace reference for the dedicated Vault-backed Secret.
- [ ] Provision the Vault secret at the referenced path with org-admin, non-org-admin, and helper-control-token fields.
- [ ] Confirm the active account/org context before production mutations.
- [x] Add a browser-only proxy override without changing Jira or model proxy settings.
- [ ] Verify the deployed pod can reach Stage through the configured proxy.
- [ ] Verify the browser MCP can perform the required UI inspection and interactions.
- [ ] Verify Jira comment, attachment, and comment-reading capabilities.
- [x] Implement retest detection for `/retest` and explicit developer requests.
- [x] Choose memory tags/metadata conventions for app, feature, environment, build, and case IDs.
- [x] Scaffold the custom workflow and instance configuration using the browser and Jira capabilities.
