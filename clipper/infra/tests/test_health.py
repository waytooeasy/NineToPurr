"""Health alerts (infra/health.py): disk, cookies, failing and idle remakes; each at most once per 6 h."""
import sqlite3
import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from infra import health  # noqa: E402

DU = namedtuple("DU", "total used free")


def con_with(rows):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE remakes (short_id TEXT, status TEXT, last_error TEXT, updated_at TEXT)")
    c.executemany("INSERT INTO remakes VALUES (?, ?, ?, datetime('now'))", rows)
    return c


def test_full_disk_empty_cookies_and_failing_runs_alert_once(tmp_path):
    ck = tmp_path / "c.txt"
    ck.write_text("")
    env = {"YTDLP_COOKIES": str(ck)}
    c = con_with([(f"s{i}", "failed", "RuntimeError: yt-dlp: cookies file") for i in range(4)])
    sent = []
    alert = lambda m: sent.append(m) or True  # noqa: E731
    state = tmp_path / "st.json"
    keys = health.check(c, alert, state, env=env, disk=DU(100, 95, 5), now=1000)
    assert set(keys) == {"disk", "cookies", "fails"} and "4 remake runs failed" in sent[2]
    assert health.check(c, alert, state, env=env, disk=DU(100, 95, 5), now=2000) == []      # not again within 6 h
    assert health.check(c, alert, state, env=env, disk=DU(100, 95, 5), now=1000 + 7 * 3600)  # reminded later


def test_healthy_system_says_nothing_and_a_fixed_problem_alerts_again_next_time(tmp_path):
    ck = tmp_path / "c.txt"
    ck.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tX\tY\n")
    env = {"YTDLP_COOKIES": str(ck)}
    c = con_with([("a", "done", None)] + [(f"s{i}", "skipped", "no VOD") for i in range(6)])
    state = tmp_path / "st.json"
    assert health.check(c, lambda m: True, state, env=env, disk=DU(100, 50, 50), now=1) == []
    assert health.check(c, lambda m: True, state, env=env, disk=DU(100, 90, 10), now=2) == ["disk"]
    assert health.check(c, lambda m: True, state, env=env, disk=DU(100, 50, 50), now=3) == []
    assert health.check(c, lambda m: True, state, env=env, disk=DU(100, 90, 10), now=4) == ["disk"]


def test_no_remake_in_a_day_while_trying_alerts(tmp_path):
    ck = tmp_path / "c.txt"
    ck.write_text("x")
    c = con_with([(f"s{i}", "skipped", "no VOD audio matches") for i in range(8)])
    keys = [k for k, _ in health.problems(c, env={"YTDLP_COOKIES": str(ck)}, disk=DU(100, 10, 90))]
    assert keys == ["no_remakes"]
