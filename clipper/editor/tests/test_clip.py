import csv
import json
import shutil
import subprocess

import pytest

import clip

PLAN = {"score": 0.8, "in": 0.0, "out": 30.0,
        "hooks": ["He lost the bet", "Chat did this to Kai", "Kai regrets everything"],
        "context_line": "Kai lost a bet to chat",
        "title": "Kai Cenat loses the bet", "music_risk": True}


def test_cap_pick():
    assert clip.cap_pick({"start": 10, "end": 200})["end"] == 70
    assert clip.cap_pick({"start": 10, "end": 30})["end"] == 30


def test_windows_cover_transcript():
    lines = [f"[{t}.0-{t+4}.0] line {t}" for t in range(0, 300, 5)]
    ws = list(clip.windows(lines))
    assert len(ws) >= 3 and "line 0" in ws[0] and "line 295" in ws[-1]


def test_writer_picks_ranks_dedupes_caps(tmp_path, monkeypatch):
    import writer
    (tmp_path / "transcript.txt").write_text("\n".join(f"[{t}.0-{t+4}.0] x" for t in range(0, 400, 5)))
    scores = iter([0.9, 0.8, 0.4, 0.3, 0.2])

    def fake(win, creator, meta=None):
        first = float(win.split("-")[0][1:])
        return {**PLAN, "score": next(scores), "in": first, "out": first + 100.0 if first == 0 else first + 20}
    monkeypatch.setattr(writer, "write_clip", fake)
    picks = clip.writer_picks(tmp_path, 3, "Kai Cenat")
    assert 1 <= len(picks) <= 3
    assert all(p["end"] - p["start"] <= 60 for p in picks)
    for a, b in zip(picks, picks[1:]):
        assert not (a["start"] < b["end"] and b["start"] < a["end"])
    assert picks[0]["context_line"] and picks[0]["hook_variant"] == 0
    assert json.loads((tmp_path / "picks.json").read_text())


def test_log_adds_columns_and_migrates_old_header(tmp_path):
    p = tmp_path / "log.csv"
    p.write_text("date,hook\n2026-01-01,old\n")
    clip.log({"date": "d", "hook": "h", "context_line": "c", "hook_variant": 0}, p)
    clip.log({"date": "d2", "hook": "h2", "context_line": "c2", "hook_variant": 1}, p)
    rows = list(csv.DictReader(open(p)))
    assert [r["hook"] for r in rows] == ["old", "h", "h2"]
    assert rows[1]["context_line"] == "c" and rows[0]["context_line"] == ""


def test_ass_has_hook_and_context(tmp_path):
    ass = tmp_path / "a.ass"
    pick = {"start": 0, "end": 10, "hook": "He lost", "context_line": "Kai lost a bet to chat"}
    clip.build_ass([{"s": 1, "e": 2, "w": "hello"}], pick, ass)
    txt = ass.read_text()
    assert "Hook,,0,0,0,,HE LOST" in txt and "Ctx,,0,0,0,,Kai lost a bet to chat" in txt


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")
def test_synthetic_render_capped_and_context_visible(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=640x360:r=30:d=75",
                    "-f", "lavfi", "-i", "sine=f=440:d=75", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                    str(src)], check=True)
    words = [{"s": 1.0, "e": 1.5, "w": "hello"}]
    base = {"start": 0.0, "end": 75.0, "hook": "He lost"}  # asks for 75 s -> must be cut to 60

    def make(name, pick):
        ass, mp4 = tmp_path / f"{name}.ass", tmp_path / f"{name}.mp4"
        clip.build_ass(words, pick, ass)
        clip.render(src, pick, ass, mp4)
        return ass, mp4

    ass, with_ctx = make("with", {**base, "context_line": "Kai lost a bet to chat"})
    _, no_ctx = make("without", base)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                "csv=p=0", str(with_ctx)], capture_output=True, text=True, check=True).stdout)
    assert 59 <= dur <= 60.5
    assert "Kai lost a bet to chat" in ass.read_text()

    def frame(mp4):
        return subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", "2", "-i", str(mp4), "-frames:v", "1",
                               "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    assert frame(with_ctx) != frame(no_ctx)  # context line is actually drawn
