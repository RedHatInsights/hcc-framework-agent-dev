# UI Testing Agent — Local Harness Plan

## Goal

Let contributors check changes to the instance definition without deploying it, contacting Jira, opening a real HCC environment, or using real test-user credentials. The harness should support both deterministic component checks and an optional one-cycle agent run.

## What has been checked so far

- The ticket preflight selected a synthetic Jira issue using in-process Jira and memory stubs.
- Headless Chromium completed a local two-step login using dummy credentials, driven directly over Chrome DevTools Protocol.
- Neither check ran the agent model or used the configured Chrome DevTools MCP. They are smoke checks, not an end-to-end agent run.

## Two run modes

### Offline checks — no model access

Run deterministic checks for target/config validation, preflight selection and retest dispatch, fake service behavior, and the local login fixture. These should work without Jira, Vertex/Claude credentials, Vault access, or a deployment.

### One-cycle agent run — optional model access

Run the actual local runner for one cycle against the same fake services and local application. This exercises the workflow prompt and MCP tool use. It requires a developer's already-approved model endpoint credentials; it must not load the repository `.env` or connect to production services. Model usage may incur cost, so the runner must clearly announce this mode before starting.

## Proposed layout

```text
harness/
  README.md                 # contributor setup and commands
  run-offline.sh            # deterministic checks; no model call
  run-agent-cycle.sh        # opt-in single cycle
  fake-jira/                # stateful Jira MCP fixture
  fake-memory/              # isolated in-memory MCP fixture
  fake-hcc/                 # local portal and two-step login page
  fake-auth/                 # dummy profile resolver/login helper
  scenarios/                # ticket, account, and expected-result fixtures
  tests/                     # preflight, MCP contract, and browser checks
```

The implementation can adjust file names, but all harness pieces should stay under the instance directory and keep test state under a temporary directory.

## Components

1. **Fake Jira MCP** — expose only the Jira tools the workflow needs, initially `jira_search`, `jira_get_issue`, and `jira_add_comment`. Keep issue data and comments in memory or a disposable local file. Record comments for assertions; reject status transitions and any unimplemented operation. Bind to loopback only.
2. **Fake memory MCP** — implement the minimal task and learning-memory calls used by the workflow. Start empty per scenario, preserve writes during a scenario, and provide a reset operation. Do not connect to the shared memory server.
3. **Fake HCC UI** — serve a local app with a two-step username/password login and one or two simple flows. Use accessible labels and roles so the agent can discover semantic locators. Include controlled success and failure states.
4. **Fake credential profiles** — map aliases such as `viewer` and `org-admin` to dummy identities accepted only by the fake login page. The helper performs login and returns alias/auth/org display metadata, never username/password values. Unknown aliases fail closed. These profiles are fixture data, not Vault entries.
5. **Browser runtime** — use the framework's `browser` environment and Chrome DevTools MCP against the local app. Bypass proxies for loopback. Never route harness traffic through Squid or a real HCC target.
6. **Runner wrapper** — create a temporary config overlay pointing Jira and memory MCP URLs to local fakes, set the UI-test workflow and `run_and_exit`, run exactly one cycle, and clean up services and state on exit. Do not mutate the contributor's normal config or persistent memory.

## Scenarios

- No labeled issue: preflight skips without starting an agent cycle.
- One labeled issue: agent reads the fake ticket and explores the local app.
- Valid alias: selected profile reaches the matching fake identity/org; report names the alias only.
- Missing or unknown alias: agent asks for clarification or pauses; it never silently falls back to a different profile.
- Login failure: result is blocked or inconclusive; the agent does not claim the requested UI flow passed.
- Successful flow: the fake Jira receives a structured report comment; issue status remains unchanged; fake memory stores the run.
- Retest: `/retest` creates a distinct second run and preserves the first run's memory record.
- Prompt injection: malicious-looking text in the synthetic ticket or page is treated as data and does not override the workflow.

## Safety requirements

- Use only loopback URLs, fixture accounts, and dummy passwords in offline mode.
- The agent process must receive local Jira and memory URLs explicitly. The harness must fail before running if either URL is not loopback.
- Do not load `.env`, read Vault/Kubernetes secrets, or inherit Jira/test-user credentials into the offline runner.
- In one-cycle mode, allow only the explicitly configured model endpoint outside loopback. Jira, memory, browser, and target UI stay local.
- Never include dummy or real passwords in model prompts, tool arguments, transcripts, Jira reports, screenshots, logs, or memory.
- Save screenshots and run artifacts only under the temporary harness directory; remove them on cleanup unless a contributor explicitly opts to retain them.

## Acceptance checks

- A contributor can run offline checks with the documented command and no secret setup.
- The fake Jira and memory services receive all expected calls and no external calls.
- The one-cycle runner exits after one issue and never reaches real Jira, stage, prod, or Squid.
- A valid alias completes the fake login while no credential value appears in captured output or persisted state.
- Missing/invalid aliases and failed login produce a safe blocked outcome.
- Retest creates a new run without overwriting prior results.
- Cleanup stops local services and leaves no tracked files or persistent test state behind.

## Current gaps

There is no reusable fake Jira/MCP harness yet. The local checkout also lacks the Chrome DevTools MCP package and the Vault-backed credential-profile helper. Implement the fixtures and helper contract before attempting a one-cycle agent run. The framework's current SSO setup supports one account through `SSO_USERNAME`/`SSO_PASSWORD`; the local fake profiles must not rely on that single-account path.
