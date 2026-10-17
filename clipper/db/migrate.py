#!/usr/bin/env python3
"""Apply schema.sql + ledger.sql to a new DB, then every migrations/NNN_*.sql not yet applied (D26).

Each file runs in its own transaction and is recorded in schema_migrations(version, applied_at).
Idempotent: a second run applies nothing. A DB that already has `clips` but no schema_migrations
(schema + ledger only) is treated as base-applied and only gets the migrations.

Usage:
  python db/migrate.py                         # DB = $CLIPPER_DB (default /opt/clipper/db/clip.db)
  python db/migrate.py --db /tmp/x.db
  python db/migrate.py --baseline 002_radar    # record a migration that was applied by hand, don't run it
"""
import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DB = "/opt/clipper/db/clip.db"
BASE_VERSION = "001_base"
NAME_RE = re.compile(r"^\d{3}_[A-Za-z0-9_]+$")


def db_path():
    return os.environ.get("CLIPPER_DB", DEFAULT_DB)


def _run(con, version, sql):
    """Run one script + its schema_migrations row atomically."""
    if not NAME_RE.match(version):
        raise ValueError(f"bad migration name: {version!r}")
    try:
        con.executescript(
            "BEGIN;\n" + sql + "\n;\n"
            f"INSERT INTO schema_migrations (version) VALUES ('{version}');\nCOMMIT;")
    except Exception:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise


def migrate(path=None, root=HERE, baseline=()):
    """Bring the DB at `path` up to date. Returns the list of versions applied (in order)."""
    path = str(path or db_path())
    root = Path(root)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')));")
        done = {r[0] for r in con.execute("SELECT version FROM schema_migrations")}
        applied = []
        if BASE_VERSION not in done:
            has_base = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='clips'").fetchone()
            if has_base:  # schema + ledger already there: just record it
                _run(con, BASE_VERSION, "")
            else:
                _run(con, BASE_VERSION, (root / "schema.sql").read_text() + "\n;\n"
                     + (root / "ledger.sql").read_text())
            applied.append(BASE_VERSION)
        for v in baseline:
            if v not in done:
                _run(con, v, "")
                done.add(v)
        for f in sorted((root / "migrations").glob("[0-9][0-9][0-9]_*.sql")):
            if f.stem not in done:
                _run(con, f.stem, f.read_text())
                applied.append(f.stem)
        return applied
    finally:
        con.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", help="DB path (default $CLIPPER_DB)")
    ap.add_argument("--baseline", action="append", default=[], metavar="VERSION",
                    help="mark a migration as already applied (e.g. 002_radar); repeatable")
    a = ap.parse_args(argv)
    applied = migrate(a.db, baseline=a.baseline)
    print("applied: " + ", ".join(applied) if applied else "up to date")


if __name__ == "__main__":
    sys.exit(main())
