---
name: pr-checklist
description: Finish a PRM build task. Use before ending any build session or opening a PR.
---
1. `pytest -q clipper` passes offline.
2. New code has tests with fixtures in the module's `tests/`.
3. Schema changes are a new `clipper/db/migrations/NNN_name.sql`; `python3 clipper/db/migrate.py` applies cleanly on a fresh DB.
4. Module `README.md`: status, how to run, env vars, next step.
5. No secrets, media, `.db` files; nothing in `.github/`, `DECISIONS.md`, `STRATEGY.md`.
6. Anything needing a decision → say so at the top of the PR body.
