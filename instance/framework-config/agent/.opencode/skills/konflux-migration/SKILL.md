---
name: konflux-migration
description: Use when onboarding a component to Konflux or migrating it between tenants or clusters. Covers release-data inventory, RPA parity, and configuration handoff.
---

### Discover the actual release path

Read the release-data repository instructions and current upstream default branch.
Confirm the application, each component/variant, source URL and revision,
source/destination tenant and cluster, intended release repositories, and owners.
Do not derive registry paths from namespace names. Ask for unresolved values
together. Treat tenant-wide migrations as inventories, not global replacements.

Trace the source Application, Component, ImageRepository, build triggers,
integration scenarios (including optionality), ReleasePlan, matched managed
ReleasePlanAdmission (RPA), constraints, and referenced secrets/config maps.
For each record preserve/adapt/create/out-of-scope. Missing Application or
Component YAML does not prove the resource is absent: verify its binding and
declare it in the destination if in scope. For first onboarding, confirm the
intended behavior instead of inventing a source baseline.

### Prepare and verify the configuration

Use destination examples for structure and source configuration for behavior.
Check whether a destination RPA already matches before adding one. Keep tenant
GitOps and managed release changes separate according to repository instructions.
Keep source releases and consumer references intact unless explicitly scoped.
Reconcile existing work on retries instead of creating duplicate resources.

For every component and variant, compare the RPA policy, per-component `public`
and `pushSourceContainer`, repository URLs and tag templates. Compare by name,
not array position. Verify intended visibility from the source or the owner:
missing `public: true` can leave an intended public repository private; never
blanket-enable it. Record reasons for intentional differences. Compare the
integration scenario's EC policy reference as well as the RPA policy.

When a source RPA exists, run the bundled helper for each source/destination
release repository pair. Set `skill_dir` to the directory containing this SKILL.md:

```sh
python "$skill_dir/check_rpa.py" \
  "$source_rpa" "$dest_rpa" "$component" "$old_repo" "$approved_repo"
```

Use absolute manifest paths. The helper checks one mapping, not the entire release graph. Account for
additional or retired mappings, renames and deliberate changes in the MR.
Check rendered namespace, release plan/admission pairing, origin, policy,
permissions and secret references. Register sources in kustomization, regenerate
manifests, inspect generated diffs and run the target repository's documented
checks. Report the commands and results.

### Publish and hand off

Follow the existing workflow for repository selection, publication and review
tracking. Request tenant CODEOWNER and managed-release review on their
respective changes.

Return MR links, validation evidence, unresolved inputs, and the next owner's
action. Distinguish proposed/merged configuration from a published image or
live deployment. A configuration-only ticket needs no live build verification.
Do not trigger builds, switch app-interface consumers, remove old resources,
or activate the bot on a downstream ticket as a side effect.
