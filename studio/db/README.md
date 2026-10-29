# DB (design only)

**Status:** not built. Build order 1 (with the `shared/` extraction).

SQLite at `/opt/studio/studio.db`. The tables and fields are the contract in [`../docs/DATA.md`](../docs/DATA.md). Migrations: `migrations/NNN_name.sql`, applied by the shared `migrate.py` on setup and every deploy; CI applies them to a fresh DB like the clipper's.
