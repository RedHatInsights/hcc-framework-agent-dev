# HCC Framework HyperShell migration draft

This prepares dispatcher profiles for framework development, manager tasks, and
quality monitoring. It does not enable the dispatcher or replace the existing
deployments. Do not enable this repository in the dispatcher until the gates
below are complete.

## Model tiers

Role-based tiers use only the existing profiles and subagents:

| Profile | Role | Model |
|---|---|---|
| `framework-config` | Root session and `framework-coordinator`: ticket coordination, review, delegation | `gpt-6.1-sol` |
| `framework-config` | `rds-upgrade`: complex, high-risk staged infrastructure work | `gpt-6.1-sol` |
| `framework-config` | `backend`, `config`, `cve`, `frontend`, `operator`, `rbac`, `tooling`: substantial implementation | `gpt-6.1-terra` |
| `manager-tasks` | Root session and `manager-task-runner`: one bounded scheduled task per cycle | `gpt-6-luna` |
| `quality-monitor` | Root session and `quality-monitor`: one bounded finding or feedback item per cycle | `gpt-6-luna` |
| `ui-test-agent` | No explicit runtime or model; profile stays inert with `preflights: []` | none |

The runner selects the session root model from `instance.yaml`. OpenCode keeps
that explicitly selected session model when `default_agent` chooses a primary
agent, so `framework-config` must use Sol at the root for the Sol coordinator;
its subagents still use their own frontmatter models. The manager and quality
roots match their single Luna primary agents.

Upstream #117 moved this developing instance's implementation roles from Luna
to Terra and set the shared root model to Terra. This draft deliberately keeps
#117's Terra tier for every implementation subagent it upgraded and moves only
the root session to Sol: the coordinator creates each session with the
`instance.yaml` root model, and coordination/review is the Sol tier's role in
the HyperShell tier policy. The reconciliation is recorded next to
`model:` in `instance/framework-config/agent/instance.yaml`.

### Catalog and allowlist gates

- The pinned runner (`dev-bot` submodule `f23332e`) declares only Luna and Terra
  under packaged `rehor-openai` defaults, but prices all three models. The
  instance-owned `opencode-deployment.json` is the effective catalog:
  `framework-config` declares Sol, Terra and Luna; `manager-tasks` and
  `quality-monitor` declare Sol and Luna. Every selected root and subagent model
  must be declared there.
- The stage model proxy's `OPENAI_ALLOWED_MODELS` in app-interface
  (`data/services/insights/platform-frontend-ai-dev/deploy.yml`) currently lists
  `gpt-6.1-sol,gpt-6-luna,gpt-6.1-terra`. The proxy is deployment-owned and fails
  closed with HTTP 403, so re-verify the live value after image promotion, a
  submodule bump, or any GitOps change. This draft does not change app-interface
  or deployment configuration.
- A submodule bump or promoted runner image can change the packaged catalog.
  Recheck every root and subagent selection against the deployment declarations
  and gateway allowlist before dispatch. Do not add roles or model declarations
  for tiers that no existing role uses.
- In representative cycles, verify usage and transcript attribution show the
  intended model per role, not only the configured value.

## Slack webhook tier-2 secrets

Each dispatched profile renders its own Slack webhook into the sandbox from
the tier-2 Kubernetes Secret `hcc-framework-rehor`, synced from the Vault path
`secrets/insights-dev/platform-experience-dev/hcc-asdlc/hcc-framework-rehor`.
The sandbox environment name is `SLACK_WEBHOOK_URL` for every profile — the
pinned coordinator's operational allowlist forwards exactly that name to
OpenCode children and the Slack helper reads it — while the Vault key selects
the per-profile webhook:

| Profile | Vault key | Sandbox env |
|---|---|---|
| `framework-config` | `SLACK_WEBHOOK_URL` | `SLACK_WEBHOOK_URL` |
| `manager-tasks` | `MANAGER_TASKS_SLACK_WEBHOOK_URL` | `SLACK_WEBHOOK_URL` |
| `quality-monitor` | `QUALITY_MONITOR_SLACK_WEBHOOK_URL` | `SLACK_WEBHOOK_URL` |

Non-secret notify settings ride the same `sandbox.env`: `framework-config`
and `quality-monitor` set `SLACK_NOTIFY_MODE: daily_digest` and
`SLACK_DIGEST_HOUR: '11'`, preserving the legacy `devbot-framework` and
`devbot-framework-quality` deployment values (daily digest at 11 UTC,
runner-triggered after each cycle). The pinned runtime reads both: the
coordinator's operational allowlist forwards `SLACK_NOTIFY_MODE` to OpenCode
children, the Slack helper defaults to `immediate` without it, and the digest
stays disabled unless `SLACK_DIGEST_HOUR` is set. `manager-tasks` declares no
digest settings — the legacy `devbot-framework-manager` deployment set none.

`ui-test-agent` declares no `sandbox:` category; it stays inert with
`preflights: []`. No webhook values or URLs belong in this repository.

Rollout dependency: rendering (Rehor #681/#688 in the pinned `f23332e`) fails
closed — dispatch is rejected when the tier-2 Secret or any referenced key is
missing — so the Secret must be provisioned with all three keys through
app-interface and the deployed dispatcher image must support rendering before
these profiles are enabled.

## Before rollout

1. Rehor core prerequisites are merged through master `f23332e`
   ([#667](https://github.com/OpenShift-Fleet/rehor/pull/667) HCC preflights,
   [#668](https://github.com/OpenShift-Fleet/rehor/pull/668) top-level env,
   [#678](https://github.com/OpenShift-Fleet/rehor/pull/678),
   [#679](https://github.com/OpenShift-Fleet/rehor/pull/679) instance env,
   [#680](https://github.com/OpenShift-Fleet/rehor/pull/680),
   [#681](https://github.com/OpenShift-Fleet/rehor/pull/681) tier-2 secret
   rendering from Kubernetes Secrets,
   [#682](https://github.com/OpenShift-Fleet/rehor/pull/682) bot instance
   identity header encoding, and
   [#688](https://github.com/OpenShift-Fleet/rehor/pull/688) sandbox.env
   delivery); the `dev-bot` submodule pins exactly that revision. The
   remaining gate on the core side is deployment: build and promote a stage
   dispatcher image containing these revisions, then build and promote a new
   HCC Framework runner image containing these profile and workflow changes.
   Verify the configured `latest` tag resolves to that compatible image
   before enabling dispatch; the tag can change. The dispatcher checks out the
   config repository and its pinned submodule separately from the baked runner
   image; their runtime, profile, and workflow contents must be compatible.
2. Confirm the three instance IDs, labels and Jira board settings against the
   current deployment. They are copied from the stage configuration; changing an
   instance ID can hide its existing tasks. The Jira sprint preflight currently
   does not include the optional bot-email candidate pass because that identity
   comes from deployment secrets; validate assigned-ticket behavior before cutover.
3. Verify dispatcher private-runtime support, model tier declarations and gateway
   allowlist, Git/Jira/memory and Slack connectivity, required environment and
   sandbox policy with the promoted image. The tier-2 Secret
   `hcc-framework-rehor` must be provisioned with all three webhook keys
   before dispatch; see "Slack webhook tier-2 secrets". Configure the
   dispatcher and repository
   in app-interface separately;
   this PR does not change GitOps. The UI-test profile is intentionally declared
   with `preflights: []`: discovery requires an image for every profile, but its
   sidecar-dependent workflow is not migrated and must not be dispatched here.
4. Plan cutover so legacy runners and dispatcher never process the same instance
   simultaneously. Each profile's `schedule:` declaration now mirrors its legacy
   KEDA window from app-interface (framework and quality: Mon-Fri 09:00-23:00
   Prague; manager: Mon/Tue/Wed/Fri 07:00-21:00 Prague), so the dispatcher
   starts no sessions outside the windows the legacy deployments used. Quality
   and weekly report preflights keep enforcing their own finer-grained Prague
   windows inside them; in-flight sessions drain past a window's end.
5. Run no-work and representative work cycles. Verify weekly PR feedback and
   merge handling; quality Jira feedback on existing and unattributed tasks;
   one violation and a completed no-ticket scan; task identity and cleanup.
   Unattributed task ownership is ambiguous and Jira bot detection is heuristic.

## Post-rollout opportunities

- Rehor #681 (in the pinned `f23332e`) renders `${{ secret('name','key') }}`
  placeholders in `sandbox.env` from tier-2 labeled Kubernetes Secrets synced
  from Vault. The Slack webhooks now use this mechanism (see "Slack webhook
  tier-2 secrets"); once the deployed dispatcher is confirmed and any further
  tier-2 Secrets are provisioned through app-interface, other confidential
  per-profile values can move from deployment-owned configuration into
  `sandbox.env` secret references instead of being passed through the
  deployment.

## Rollback

Remove this repository from dispatcher configuration and allow in-flight sessions
to drain before restoring the existing runners. Keep the previous runner image,
deployment settings, and legacy Python preflights available. Verify the dispatcher
has stopped launching these profiles before enabling the old schedules.
