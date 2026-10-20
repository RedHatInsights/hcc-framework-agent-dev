# UI testing agent deployment

## Runtime layout

Use the instance-specific OpenShift template at
[`deploy/ui-test-agent/template.yaml`](../../deploy/ui-test-agent/template.yaml).
It adds a `stage-login-helper` sidecar to the bot pod without changing the
shared deployment template used by other agents. Both containers use the
runner image. The helper binds to pod loopback on port 8768 and reaches the
existing Chromium CDP endpoint on port 9222; it needs no Service or Route.

The helper's health endpoint is probed from inside the sidecar. The bot waits
for it before starting. At the start of each agent work cycle, the framework
uses a loopback-only control route to reset the helper's one-password-attempt
guard. A failed password submission blocks further attempts during that
ticket's cycle, while later tickets can start fresh.

Chromium receives `UI_BROWSER_PROXY` separately from the bot's `HTTP_PROXY` and
`HTTPS_PROXY`. The template points it at the existing `devbot-proxy`; Jira,
memory, and model traffic keep their current routing. The proxy allowlist
includes Red Hat domains, but Stage reachability still needs validation from
the deployed pod.

## Credential Secret

Create a dedicated Vault-backed Kubernetes Secret in the same namespace as the
bot Deployment. The App Interface namespace config references
`app-interface/platform-frontend-ai-dev/stage/ui-test-agent-credentials`
(initial Vault version `1`) and creates the Kubernetes Secret
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

Also provide `helper-control-token`, a random value used only to authorize the
loopback cycle-reset route. Kubernetes passes it to the helper sidecar and the
bot runner as environment variables; the runner removes its copy before
starting model tools. The token is excluded from the helper's profile-file
mount. Set these Vault fields from the existing `insights-chrome` Stage
credentials: `org-admin.username` from `CHROME_E2E_USERNAME`,
`org-admin.password` from `CHROME_E2E_PASSWORD`, `non-org-admin.username` from
`E2E_NON_ADMIN_USER`, and `non-org-admin.password` from
`E2E_NON_ADMIN_PASSWORD`. Generate `helper-control-token` separately; do not
reuse a login credential.

The Konflux `chrome-credentials-secret` is in the Konflux tenant namespace and
cannot be mounted directly by this agent. Provision the referenced App
Interface Vault secret with the field mapping above; the namespace reference
expects its first version to be `1`. Do not copy credential values into this
repo, Jira, or model configuration. If the Vault secret already exists at a
different version, update the namespace reference to that version.

## Deployment handoff

The repository template, framework wiring, paused App Interface Stage resource,
and namespace reference for the dedicated Secret are prepared. The Vault data
must still be provisioned at the referenced path before the resource can be
reconciled. The current resource targets
`platform-frontend-ai-dev-stage`, where the quality monitor shares the proxy
and memory server.

Keep the first deployment paused (`BOT_REPLICAS: '0'` and
`KEDA_DESIRED_REPLICAS: '0'`) while validating:

1. The helper sidecar becomes ready and the bot can reach its MCP endpoint on
   `127.0.0.1:8768`.
2. Chromium reaches Stage through `devbot-proxy` and the login helper confirms
   the signed-in User Avatar control.
3. `org-admin` and `non-org-admin` resolve to the intended accounts and the
   UI shows the expected org and role.
4. A failed password submission blocks another attempt in the same work cycle;
   a later cycle resets the guard.
5. The Jira report, logs, and memory contain no username or password.

Only after these checks should the App Interface deployment be enabled for the
`hcc-ui-test` intake label and its normal schedule.
