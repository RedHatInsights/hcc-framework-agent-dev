# UI testing agent deployment

## Runtime layout

Use the instance-specific OpenShift template at
[`deploy/ui-test-agent/template.yaml`](../../deploy/ui-test-agent/template.yaml).
It adds a `stage-login-helper` sidecar to the bot pod without changing the
shared deployment template. The helper starts the agent's Chromium with the
Stage proxy, then serves its loopback HTTP API on port 8768. Chromium's
DevTools endpoint is on the same pod loopback at port 9222. For sign-in, the
helper opens a separate temporary Chromium process without a TCP DevTools
endpoint, submits credentials there, then copies the authenticated cookies and
local storage into the agent browser. The agent calls `POST /sign-in` through
the already permitted `Bash` tool and passes only a configured profile alias.
The helper exposes no MCP tool and needs no Service or Route.

An HCC-owned bot wrapper waits for the helper health check before starting the
shared bot entrypoint. When that entrypoint starts its browser preset, it sees
the sidecar's existing Chromium session and does not launch a second browser.
The helper's `UI_BROWSER_PROXY` points Chromium at `devbot-proxy`; Jira,
memory, and model traffic keep their existing routing. The proxy allowlist
includes Red Hat domains, but Stage reachability still needs validation from
the deployed pod.

The stage-login-helper container writes one-line JSON diagnostics to stderr
for startup and each login attempt. Event, status, and reason_code identify
the outcome; browser failures also include an allowlisted phase, and login
attempts include elapsed milliseconds. These records omit aliases, credentials,
URLs, raw exceptions, and browser output. A Lockdown exception or rendered
Lockdown page is logged as status blocked with reason_code proxy_lockdown.
Explicit invalid or incorrect username or password messages are classified as
status authentication_failed with reason_code sso_rejected_credentials; the
message text itself is not logged. Other SSO failures retain a generic reason
code and phase.

## Credential Secret

Create a dedicated Vault-backed Kubernetes Secret in the same namespace as the
bot Deployment. The App Interface namespace config references
`app-interface/platform-frontend-ai-dev/stage/ui-test-agent-credentials`
(currently at Vault version `3`) and creates the Kubernetes Secret
`ui-test-agent-credentials`. The helper mounts it read-only at
`/var/run/ui-test-credentials`. The bot container does not mount this volume or
receive the profile values as environment variables.

Secret keys are file names consumed by the helper:

| Secret key | Profile |
| --- | --- |
| `org-admin.username` | `org-admin` |
| `org-admin.password` | `org-admin` |
| `non-org-admin.username` | `non-org-admin` |
| `non-org-admin.password` | `non-org-admin` |

Set these Vault fields from the existing `insights-chrome` Stage credentials:
`org-admin.username` from `CHROME_E2E_USERNAME`,
`org-admin.password` from `CHROME_E2E_PASSWORD`, `non-org-admin.username` from
`E2E_NON_ADMIN_USER`, and `non-org-admin.password` from
`E2E_NON_ADMIN_PASSWORD`. A previously configured `helper-control-token` is no
longer consumed and can be removed during the next Vault update.

The Konflux `chrome-credentials-secret` is in the Konflux tenant namespace and
cannot be mounted directly by this agent. Provision the referenced App
Interface Vault secret with the field mapping above. Keep the namespace's Vault
version reference aligned if the secret is updated. Do not copy credential
values into this repo, Jira, or model configuration.

## Deployment handoff

The repository template, HCC-owned startup wrapper, paused App Interface Stage
resource, and namespace reference for the dedicated Secret are prepared. The
current resource targets
`platform-frontend-ai-dev-stage`, where the quality monitor shares the proxy
and memory server.

Keep the first deployment paused (`BOT_REPLICAS: '0'` and
`KEDA_DESIRED_REPLICAS: '0'`) while validating:

1. The helper sidecar starts Chromium and becomes ready; the HCC wrapper waits
   before starting the bot.
2. The private login browser reaches Stage through `devbot-proxy`, signs in,
   and installs the session in the agent browser without exposing the password
   through its CDP endpoint.
3. `org-admin` and `non-org-admin` each resolve to the intended accounts after
   the cooldown, including when switching personas without restarting the sidecar.
4. An immediate repeated login call is blocked for five minutes. The workflow
   stops after an authentication failure; a later cycle can retry after the
   cooldown without restarting the sidecar.
5. The Jira report, logs, and memory contain no username or password.

Only after these checks should the App Interface deployment be enabled for the
`hcc-ui-test` intake label and its normal schedule.
