import sqlite3
from pathlib import Path

import pytest

import migrate

DB = Path(__file__).resolve().parents[1]
VERSIONS = [p.stem for p in sorted((DB / "migrations").glob("[0-9]*_*.sql"))]


def versions(path):
    c = sqlite3.connect(path)
    try:
        return [r[0] for r in c.execute("SELECT version FROM schema_migrations ORDER BY version")]
    finally:
        c.close()


def cols(path, table):
    c = sqlite3.connect(path)
    try:
        return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
    finally:
        c.close()


def test_fresh_db_gets_everything(tmp_path):
    p = tmp_path / "sub" / "clip.db"
    applied = migrate.migrate(p)
    assert applied == ["001_base", *VERSIONS]
    assert versions(p) == sorted(["001_base", *VERSIONS])
    assert {"state", "context_line", "hooks_json", "title", "music_risk"} <= cols(p, "clips")
    assert "clips_id" in cols(p, "radar_candidates")
    c = sqlite3.connect(p)
    n = c.execute("SELECT count(*) FROM sqlite_master WHERE name IN ('ledger','approvals','radar_candidates')")
    assert n.fetchone()[0] == 3


def test_idempotent(tmp_path):
    p = tmp_path / "clip.db"
    migrate.migrate(p)
    assert migrate.migrate(p) == []
    assert len(versions(p)) == 1 + len(VERSIONS)


def test_upgrade_db_with_only_schema_and_ledger(tmp_path):
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.executescript((DB / "schema.sql").read_text())
    c.executescript((DB / "ledger.sql").read_text())
    c.execute("INSERT INTO creators (id, name) VALUES (1, 'Kai Cenat')")
    c.execute("INSERT INTO sources (id, creator_id, url) VALUES (1, 1, 'https://x/vod')")
    c.execute("INSERT INTO clips (source_id, start_s, end_s) VALUES (1, 0, 30)")
    c.commit()
    c.close()
    assert migrate.migrate(p) == ["001_base", *VERSIONS]  # base is only recorded, not re-run
    c = sqlite3.connect(p)
    assert c.execute("SELECT state FROM clips").fetchone()[0] == "found"  # data kept, default state


def test_baseline_skips_a_hand_applied_migration(tmp_path):
    p = tmp_path / "vm.db"
    c = sqlite3.connect(p)
    for f in ["schema.sql", "ledger.sql", "migrations/002_radar.sql"]:
        c.executescript((DB / f).read_text())
    c.close()
    with pytest.raises(sqlite3.OperationalError):  # table exists; nothing is left half-applied
        migrate.migrate(p)
    assert "002_radar" not in versions(p)
    migrate.migrate(p, baseline=["002_radar"])
    assert "state" in cols(p, "clips") and "clips_id" in cols(p, "radar_candidates")


def test_failed_migration_rolls_back_and_stops(tmp_path):
    root = tmp_path / "root"
    (root / "migrations").mkdir(parents=True)
    for f in ["schema.sql", "ledger.sql"]:
        (root / f).write_text((DB / f).read_text())
    (root / "migrations" / "002_ok.sql").write_text("CREATE TABLE a (x);")
    (root / "migrations" / "003_bad.sql").write_text("CREATE TABLE b (x); INSERT INTO nope VALUES (1);")
    p = tmp_path / "c.db"
    with pytest.raises(sqlite3.OperationalError):
        migrate.migrate(p, root=root)
    assert versions(p) == ["001_base", "002_ok"]
    assert "b" not in {r[0] for r in sqlite3.connect(p).execute("SELECT name FROM sqlite_master")}
    (root / "migrations" / "003_bad.sql").write_text("CREATE TABLE b (x);")
    assert migrate.migrate(p, root=root) == ["003_bad"]


def test_db_path_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_DB", str(tmp_path / "env.db"))
    migrate.main([])
    assert (tmp_path / "env.db").exists()
