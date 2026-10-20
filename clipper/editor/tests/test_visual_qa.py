"""Visual check of the finished Short (editor/visual_qa.py). Offline: fake vision, fake frame grab."""
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

import visual_qa as V

DB = Path(__file__).resolve().parents[2] / "db"


def test_parse_keeps_known_codes_only():
    assert V.parse('{"ok": true}') == {"ok": True, "issues": []}
    r = V.parse('sure: {"ok": false, "issues": [{"code": "double_captions", "frame": 2}, {"code": "vibes"}]}')
    assert r == {"ok": False, "issues": [{"code": "double_captions", "frame": 2}]}
    assert V.parse('{"ok": false, "issues": [{"code": "vibes"}]}') is None    # nothing actionable
    assert V.parse("no json") is None


def test_check_never_raises_and_never_blocks(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert V.check(tmp_path / "x.mp4")["ok"] is None                             # no key
    boom = lambda imgs: (_ for _ in ()).throw(RuntimeError("API down"))           # noqa: E731
    r = V.check("x.mp4", vision=boom, grab=lambda v: [b"a", b"b", b"c"])
    assert r["ok"] is None and "API down" in r["error"]
    r = V.check("x.mp4", vision=lambda imgs: '{"ok": false, "issues": [{"code": "broken_glyphs"}]}',
                grab=lambda v: [b"a", b"b", b"c"])
    assert r["ok"] is False and r["issues"][0]["code"] == "broken_glyphs"


@pytest.fixture
def con(tmp_path):
    c = sqlite3.connect(":memory:")
    for f in ["schema.sql", "ledger.sql", *sorted(p.relative_to(DB).as_posix() for p in (DB / "migrations").glob("*.sql"))]:
        c.executescript((DB / f).read_text())
    c.execute("INSERT INTO creators (id, name) VALUES (1, 'k')")
    c.execute("INSERT INTO sources (id, creator_id, url) VALUES (1, 1, 'u')")
    for i in (1, 2, 3):
        f = tmp_path / f"{i}.mp4"
        f.write_bytes(b"x")
        c.execute("INSERT INTO clips (id, source_id, start_s, end_s, state, file_path) VALUES (?, 1, 0, 10, 'qc_passed', ?)",
                  (i, str(f)))
    c.execute("UPDATE clips SET state='published' WHERE id=3")
    c.commit()
    return c


def test_run_checks_each_qc_passed_clip_once(con, monkeypatch):
    monkeypatch.setenv("VISUAL_QA", "1")
    calls = []

    def vision(imgs):
        calls.append(len(imgs))
        return '{"ok": true}' if len(calls) == 1 else '{"ok": false, "issues": [{"code": "blurry_panel"}]}'
    res = V.run(con, vision=vision, grab=lambda v: [b"a", b"b", b"c"])
    assert res["passed"] == [1] and res["failed"] == {2: ["blurry_panel"]} and calls == [3, 3, 3]  # fail = 2 looks
    assert res["rerender"] == []
    assert json.loads(con.execute("SELECT visual_qa FROM clips WHERE id=2").fetchone()[0])["ok"] is False
    assert V.run(con, vision=vision, grab=lambda v: [b"a"]) == {"passed": [], "failed": {}, "unchecked": [], "rerender": []}
    monkeypatch.setenv("VISUAL_QA", "0")
    con.execute("UPDATE clips SET visual_qa=NULL")
    assert V.run(con, vision=vision) == {"passed": [], "failed": {}, "unchecked": [], "rerender": []}   # off


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")
def test_frames_grabs_three_jpegs(tmp_path):
    v = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30:duration=6",
                    "-pix_fmt", "yuv420p", str(v)], check=True)
    imgs = V.frames(v)
    assert len(imgs) == 3 and all(b[:2] == b"\xff\xd8" for b in imgs)            # JPEG magic


def test_double_captions_teach_the_streamer_and_rerender_once(con, monkeypatch, tmp_path):
    # Valkyrae shows live captions too: found by the check on 2026-10-20, not by hand.
    monkeypatch.setenv("VISUAL_QA", "1")
    con.execute("INSERT INTO radar_candidates (clip_id, creator, title, url, view_count, clip_created_at,"
                " views_per_hour, clips_id) VALUES ('a', 'Valkyrae', '', 'u', 1, '2026-10-20T00:00:00Z', 1, 1)")
    con.execute("UPDATE clips SET visual_qa='{\"ok\": true}' WHERE id=2")
    con.commit()
    dbl = lambda imgs: '{"ok": false, "issues": [{"code": "double_captions", "frame": 2}]}'   # noqa: E731
    res = V.run(con, vision=dbl, grab=lambda v: [b"a", b"b", b"c"])
    assert res["rerender"] == [1]
    assert con.execute("SELECT state, visual_qa FROM clips WHERE id=1").fetchone() == ("needs_rerender", None)
    assert con.execute("SELECT creator, own_captions FROM creator_flags").fetchall() == [("valkyrae", 1)]
    import clip
    db = tmp_path / "c.db"
    disk = sqlite3.connect(db)
    con.backup(disk)
    disk.close()
    assert "valkyrae" in clip.own_caption_logins(db=str(db))                   # the Editor now skips ours
    # after the re-render: still double captions -> no second automatic retry, it waits for a tap
    con.execute("UPDATE clips SET state='qc_passed' WHERE id=1")
    con.commit()
    res = V.run(con, vision=dbl, grab=lambda v: [b"a", b"b", b"c"])
    assert res["failed"] == {1: ["double_captions"]} and res["rerender"] == []


def test_prompt_names_our_own_header_so_it_is_not_double_captions():
    p = V.prompt_for({"hook": "Lacy's hands are full today", "header": "white_box"})
    assert "\"Lacy's hands are full today\"" in p and "WHITE BOX" in p and "is NOT ours" in p
    assert V.prompt_for(None) == V.PROMPT
    r = V.check("x.mp4", vision=lambda imgs: "I think it looks fine", grab=lambda v: [b"a"] * 3)
    assert r["ok"] is None and r["raw"].startswith("I think")                     # unreadable: keep the reply


def test_a_failure_needs_a_second_look_to_count():
    replies = iter(['{"ok": false, "issues": [{"code": "double_captions"}]}', '{"ok": true}'])
    r = V.check("x.mp4", vision=lambda imgs: next(replies), grab=lambda v: [b"a"] * 3)
    assert r["ok"] is True and r["unconfirmed"] == ["double_captions"]
    replies = iter(['{"ok": false, "issues": [{"code": "double_captions"}, {"code": "black_bars"}]}',
                    '{"ok": false, "issues": [{"code": "double_captions"}]}'])
    r = V.check("x.mp4", vision=lambda imgs: next(replies), grab=lambda v: [b"a"] * 3)
    assert r["ok"] is False and [i["code"] for i in r["issues"]] == ["double_captions"]
