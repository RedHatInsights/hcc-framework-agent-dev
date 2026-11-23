# HCC Framework HyperShell migration draft

This prepares dispatcher profiles for framework development, manager tasks, and
quality monitoring. It does not enable the dispatcher or replace the existing
deployments. Do not enable this repository in the dispatcher until the gates
below are complete.

## Before rollout

1. Merge [Rehor PR #667](https://github.com/OpenShift-Fleet/rehor/pull/667) and
   [PR #668](https://github.com/OpenShift-Fleet/rehor/pull/668), then deploy a
   dispatcher image containing both. Top-level `env` requires #668; older
   dispatchers do not read it. Update the `dev-bot` submodule to a
   merged Rehor revision containing the matching sandbox runtime, then build and
   promote a new HCC Framework runner image containing these profile and workflow
   changes. Verify the configured `latest` tag resolves to that compatible image
   before enabling dispatch; the tag can change. The dispatcher checks out the
   config repository and its pinned submodule separately from the baked runner
   image; their runtime, profile, and workflow contents must be compatible.
2. Confirm the three instance IDs, labels and Jira board settings against the
   current deployment. They are copied from the stage configuration; changing an
   instance ID can hide its existing tasks. The Jira sprint preflight currently
   does not include the optional bot-email candidate pass because that identity
   comes from deployment secrets; validate assigned-ticket behavior before cutover.
3. Verify dispatcher private-runtime support, model access, Git/Jira/memory and
   Slack connectivity, required environment and sandbox policy with the promoted
   image. Configure the dispatcher and repository in app-interface separately;
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

## Rollback

Remove this repository from dispatcher configuration and allow in-flight sessions
to drain before restoring the existing runners. Keep the previous runner image,
deployment settings, and legacy Python preflights available. Verify the dispatcher
has stopped launching these profiles before enabling the old schedules.
