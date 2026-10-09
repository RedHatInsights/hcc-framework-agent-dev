# UI testing agent local harness

This harness gives contributors a repeatable, secret-free way to check the UI
testing instance before deploying it. Its default checks need only Python 3 and
use synthetic Jira, memory, and login data. They do not load `.env`, call Jira,
start the agent model, read Vault/Kubernetes secrets, or contact a HCC target.

## Run offline checks

From the repository root:

```sh
./instance/ui-test-agent/harness/run-offline.sh
```

The tests exercise the actual UI-test preflight script with in-process Jira and
memory fakes, verify ticket selection and `/retest` dispatch, check the fake
credential-profile boundary, and check the local fake HCC page and login
handler. They bind no sockets. Test state lives in memory and is discarded
when the command exits.

To run the checks directly:

```sh
python3 -m unittest discover \
  -s instance/ui-test-agent/harness/tests -v
```

## Fixtures

- `fake_services.py` provides narrow, stateful Jira and memory fakes for the
  offline preflight contract. Jira supports search, issue reads, and comments;
  unsupported operations (including status changes) fail closed.
- `fake_mcp_server.py` exposes those fakes as optional loopback MCP services.
  Each process starts with a fresh synthetic issue or empty memory.
- `fake_auth.py` resolves only the fixture aliases `viewer` and `org-admin`.
  `login_profile()` passes dummy credentials directly to a supplied login
  callback and returns display metadata only. Callers cannot retrieve a
  credential through the public helper interface.
- `fake_hcc/server.py` serves a two-step accessible login and a small local
  console flow. It binds to loopback and accepts only fixture credentials.

To view the fixture in a browser, start it separately:

```sh
python3 instance/ui-test-agent/harness/fake-hcc/server.py
```

Then open `http://127.0.0.1:8765`. Stop it with Ctrl+C. The default offline
suite tests the same page and authentication handler without binding a socket.

For an optional real Chromium login smoke check, keep the fixture server
running and use a second terminal with Node 22+ and Chromium:

```sh
CHROME_BIN=/path/to/chromium node \
  instance/ui-test-agent/harness/browser-login-smoke.mjs viewer
```

The smoke check drives Chromium directly over CDP, verifies the two-step flow,
checks that a wrong password is rejected, confirms that successful login
clears the password field, and opens Subscriptions. It uses only the dummy profile and loopback;
it does not run the agent or Chrome DevTools MCP. It prints the alias and
pass/fail state, never the username or password.

The fixture profile file contains intentionally fake values. Never copy real
credentials into this directory. The fake login endpoint and browser page are
only suitable for local harness use.

To use a local test account instead of the dummy fixture values, set
`UI_HARNESS_USERNAME` and `UI_HARNESS_PASSWORD`. Both must be set. The selected
alias defaults to `viewer` and can be changed with `UI_HARNESS_PROFILE=org-admin`;
the override applies only to that alias. The fake server and browser smoke read
these variables locally. Keep them out of ticket text, model prompts, reports,
and memory records.

To start the MCP fixtures, use two terminals:

```sh
./instance/ui-test-agent/harness/run-fake-mcp.sh jira
./instance/ui-test-agent/harness/run-fake-mcp.sh memory
```

The default endpoints are `http://127.0.0.1:8766/mcp` and
`http://127.0.0.1:8767/mcp`. The memory fixture also serves the read-only
`/api/tasks` endpoint used by preflight capacity checks. `uv` prepares the
dev-bot Python environment if needed. Do not point an agent at shared Jira or
memory services when using this fixture.

## Run one model-driven cycle

Stage is the default target. The runner needs Chromium, `uv`, Node.js 22+, and
Chrome DevTools MCP. Install Chrome DevTools MCP once:

```sh
npm install --global chrome-devtools-mcp
```

Configure the model endpoint and stage test account in the shell, then run one
synthetic Jira issue:

```sh
export ANTHROPIC_API_KEY
export UI_TEST_USERNAME
export UI_TEST_PASSWORD
./instance/ui-test-agent/harness/run-agent-cycle.sh --allow-model
```

Use a non-secret alias with `--profile <alias>`; it defaults to `viewer`.
`UI_TEST_USERNAME` and `UI_TEST_PASSWORD` are read only by the local
stage-login helper. The helper types them into the browser through CDP, clears
the sign-in fields after submission when possible, and never returns them to
the model, bot process, Jira, report, or memory. The helper only fills standard
username/password forms on the stage console and approved Red Hat sign-in
hosts. The agent inspects the result and confirms the account/org context.
MFA, CAPTCHA, or unsupported sign-in forms remain a reported blocker.

The browser alone uses `http://squid.corp.redhat.com:3128` for stage traffic;
Jira and memory stay on local fixtures. The stage issue is read-only and asks
the agent to explore Subscriptions and Inventory. The runner does not deploy
anything or connect to real Jira or shared memory. Do not use production
credentials or set this harness up for production. Model calls may incur cost.

For a Vertex proxy, set `CLAUDE_CODE_USE_VERTEX=true`,
`CLAUDE_CODE_SKIP_VERTEX_AUTH=true`, `ANTHROPIC_VERTEX_BASE_URL`, and
`ANTHROPIC_VERTEX_PROJECT_ID` instead of `ANTHROPIC_API_KEY`. Optionally set
`UI_HARNESS_MODEL` to override the model in `dev-bot/config.json`.

Use the entirely local simulated UI with `--target local --allow-model`. That
mode accepts only `viewer` and `org-admin`, and optional `UI_HARNESS_USERNAME`
plus `UI_HARNESS_PASSWORD` are fixture-only values. Never use real HCC
credentials in local mode.

The temporary bot workspace is deleted after the cycle. The printed results
directory is retained under `/tmp/ui-test-agent-results-*` and contains the
Jira report, fixture state, costs, logs, and model transcript. The runner
scrubs configured UI credentials from persisted text files and records
whether it detected a leak. Optional controls include `--max-turns 20` and
`--timeout 600`.

## What this does not verify

The offline tests do not launch Claude/Vertex, use Chrome DevTools MCP, or
assess the model's exploration and reporting quality. Use the opt-in cycle
above to exercise those parts. It must not reuse the developer `.env` or
connect real Jira, shared memory, production, or Squid for any purpose outside
the stage browser session. The model tools are not isolated by an OS-level
network sandbox; keep fixture scenarios trusted and local. Do not run the
normal bot launcher for this harness.

For harness goals and the planned full-cycle acceptance checks, see
[`../TEST-HARNESS-PLAN.md`](../TEST-HARNESS-PLAN.md).
