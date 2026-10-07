# UI test request

Copy this into the Jira ticket description. A rough description is enough to start; formal acceptance criteria and detailed test cases are optional.

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
For production changes, state whether data-changing checks are in scope and note any account constraints. The approved test account determines its existing org. Do not include credentials in Jira.

**Access or test data notes:**
Reference the approved account or access process; do not paste passwords or tokens.

**Anything else that may help?**
Known limitations, related tickets, previous results, or feature-owner context.
```

The agent derives an initial test plan from the description and refines it through exploration. It asks follow-up questions only when missing target, access, expected behavior, or safety boundaries prevent a useful or safe run.
