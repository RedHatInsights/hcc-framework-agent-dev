# UI Testing Agent — Local Harness Plan

## Goal

Let contributors check changes to the instance definition without deploying it or contacting real Jira. Deterministic checks use only fakes; the optional model cycle uses fake Jira and memory with stage as its default UI target.

## What has been checked so far

- The ticket preflight selected a synthetic Jira issue using in-process Jira and memory stubs.
- Headless Chromium completed a local two-step login using dummy credentials, driven directly over Chrome DevTools Protocol.
- Neither check ran the agent model or used the configured Chrome DevTools MCP. They are smoke checks, not an end-to-end agent run.

## Implementation status

The contributor harness includes a no-network offline suite, fake Jira and
memory services, a local console fixture, and an opt-in one-cycle model runner.
Stage is the default target: the runner starts fake Jira and memory, opens stage
in Chromium through Squid, and provides an isolated local login helper for the
environment-supplied test account. The model receives no login credentials.
`--target local` selects the simulated console fixture. Reports, fixture
state, costs, logs, and transcript are retained in a temporary results
directory. Model use requires an explicit endpoint setup and `--allow-model`.

The offline suite exercises preflight and fixture behavior without starting
the bot or model. The one-cycle runner is implemented but has not been run
against a live model endpoint in this checkout.

## Two run modes

### Offline checks — no model access

Run deterministic checks for target/config validation, preflight selection and retest dispatch, fake service behavior, and the local login fixture. These should work without Jira, Vertex/Claude credentials, Vault access, or a deployment.

### One-cycle agent run — optional model access

Run the actual runner for one cycle against fake Jira and memory. Stage is the default UI target; this exercises the workflow prompt, MCP tool use, browser proxy, and local credential helper against stage. It requires explicitly configured model endpoint and stage test-account environment variables plus `--allow-model`; it must not load the repository `.env` or connect to real Jira or shared memory. Model usage may incur cost, so the runner clearly announces the target before starting.

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
5. **Browser runtime** — use Chrome DevTools MCP with desktop Chromium. In local mode, access the loopback app directly. In stage mode, route browser traffic through Squid while keeping Jira and memory local.
6. **Runner wrapper** — create a temporary config overlay pointing Jira and memory MCP URLs to local fakes, set the UI-test workflow and `run_and_exit`, run exactly one cycle, and clean up services and the workspace on exit. Do not mutate the contributor's normal config or persistent memory.

## Scenarios

- No labeled issue: preflight skips without starting an agent cycle.
- One labeled issue: the Stage-default cycle reads a synthetic ticket and explores Stage; explicit `--target local` exercises the local fake console.
- Valid alias: selected profile reaches the matching fake identity/org; report names the alias only.
- Missing or unknown alias: agent asks for clarification or pauses; it never silently falls back to a different profile.
- Login failure: result is blocked or inconclusive; the agent does not claim the requested UI flow passed.
- Successful flow: the fake Jira receives a structured report comment; issue status remains unchanged; fake memory stores the run.
- Retest: `/retest` creates a distinct second run and preserves the first run's memory record.
- Prompt injection: malicious-looking text in the synthetic ticket or page is treated as data and does not override the workflow.

## Safety requirements

- Use only loopback URLs, fixture accounts, and dummy passwords in offline and local modes.
- The agent process must receive local Jira and memory URLs explicitly in every one-cycle mode.
- Do not load `.env` or read Vault/Kubernetes secrets. In stage mode, pass the two test-account environment variables only to the local login helper, not to the bot/model process.
- In stage one-cycle mode, configure Jira and memory to loopback fixtures and route only the browser's UI traffic through the configured Squid proxy. The explicitly configured model endpoint is also used.
- Never include dummy or real passwords in model prompts, tool arguments, transcripts, Jira reports, screenshots, logs, or memory.
- Save screenshots and run artifacts only under the printed, unique temporary results directory. Keep that directory for review; clean up the disposable workspace and local services when the cycle exits.
- The runner does not create an OS-level network sandbox for model tools. Keep model-cycle scenarios trusted.

## Acceptance checks

- A contributor can run offline checks with the documented command and no secret setup.
- The fake Jira and memory services receive all expected calls and no external calls.
- The one-cycle runner exits after one synthetic issue, uses fake Jira and memory, and opens the stage target through Squid (or loopback UI in local mode).
- Stage credentials are entered by the local helper and do not appear in model prompts, Jira, reports, memory, or persisted artifacts.
- Missing/invalid aliases and failed login produce a safe blocked outcome.
- Retest creates a new run without overwriting prior results.
- Cleanup stops local services and leaves no tracked files or persistent test state behind.

## Current gaps

The stage runner and local credential helper are implemented but have not been exercised against stage or a live model endpoint in this checkout. Contributors need Chromium, Chrome DevTools MCP, model credentials, and a stage test account in `UI_TEST_USERNAME`/`UI_TEST_PASSWORD`. The separate local fixture mode uses `UI_HARNESS_USERNAME`/`UI_HARNESS_PASSWORD` and does not test real SSO. The deployed instance still requires its planned Vault-backed multi-profile helper.
