---
description: Implements insights-rbac changes in Django and Django REST Framework.
mode: subagent
model: rehor-openai/gpt-6-luna
request:
  body:
    reasoning:
      effort: medium
permissions:
  - { action: subagent, resource: "*", effect: deny }
---

## insights-rbac Guidelines

Work on `insights-rbac`, a Django 5.2 / Django REST Framework service with
PostgreSQL 16, Redis, and Celery.

- Main areas: `rbac/` Django project, `management/` roles/groups/permissions,
  `api/` tenant and serializers, `tests/`, and `scripts/`.
- Local Docker Compose needs the external `rbac-network`; development mode uses
  `DEVELOPMENT=True`, server port 9080, and database port 15432. Apply migrations
  and seeds explicitly after startup.
- Run fast tests with `make unittest-fast`; use targeted `tox -e py312-fast --
  <test>` for focused checks. Full tests use `make unittest`.
- Use `make lint`, `make format`, and `make typecheck` as relevant. Python 3.12,
  line length 119, Pipenv dependency management.
- Identity is handled by `x-rh-identity`; tenancy is keyed by `org_id`.
- Do not edit system roles directly. Custom permissions use
  `app:resource:action`. Celery connects to Redis by hostname `redis`.
- Check `settings.py`, middleware, migrations, and surrounding tests before
  implementation; follow existing API and database patterns.
