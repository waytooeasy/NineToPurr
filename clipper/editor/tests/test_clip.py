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


def test_ass_market_style(tmp_path):
    ass = tmp_path / "a.ass"
    pick = {"start": 0, "end": 10, "hook": "He lost", "context_line": "Kai lost a bet to chat"}
    words = [{"s": 1, "e": 1.4, "w": "and"}, {"s": 1.4, "e": 2, "w": "zoom"}, {"s": 2, "e": 2.5, "w": "in"}]
    clip.build_ass(words, pick, ass)
    txt = ass.read_text()
    assert "HE LOST" in txt and "0:00:02.50,Hook" in txt.replace("0:00:00.00,", "")  # hook only 2.5 s
    assert "Kai lost a bet to chat" not in txt and "Ctx" not in txt               # no banner
    caps = [l for l in txt.splitlines() if ",Cap," in l]
    assert len(caps) == 2                                                          # 2 words per line
    assert "AND {\\c&H0000E5FF&}ZOOM{\\c&H00FFFFFF&}" in caps[0]                # keyword in yellow
    assert "Montserrat Black" in txt and "\\pos(540,1080)" in caps[0]


def test_no_emoji_on_screen_but_watermark(tmp_path, monkeypatch):
    # Lucas 2026-10-19: emoji in the video text render as boxes ("He really said never seen this 😭").
    monkeypatch.delenv("CLIPPER_WATERMARK", raising=False)
    ass = tmp_path / "a.ass"
    pick = {"start": 0, "end": 10, "hook": "He really said never seen this 😭"}
    words = [{"s": 1, "e": 1.5, "w": "no"}, {"s": 1.5, "e": 2, "w": "way🔥"}, {"s": 2, "e": 2.4, "w": "😭"}]
    clip.build_ass(words, pick, ass)
    txt = ass.read_text()
    assert "HE REALLY SAID NEVER SEEN THIS" in txt
    assert not any(ord(ch) > 0x2000 for ch in txt)                                 # no emoji anywhere
    mark = [l for l in txt.splitlines() if ",Mark," in l]
    assert len(mark) == 1 and "@Peakz.Recaps" in mark[0] and "0:00:10.00" in mark[0]   # whole clip
    monkeypatch.setenv("CLIPPER_WATERMARK", "")
    clip.build_ass(words, {"start": 0, "end": 10, "hook": "😭"}, ass)
    txt = ass.read_text()
    assert ",Mark," not in txt and ",Hook," not in txt                             # emoji-only hook dropped


def test_streamer_with_own_live_captions_gets_no_second_track(tmp_path):
    # Sykkuno burns live captions into his stream; ours on top made two caption tracks (2026-10-20).
    assert "sykkuno" in clip.own_caption_logins()
    ass = tmp_path / "a.ass"
    words = [{"s": 1, "e": 1.5, "w": "my"}, {"s": 1.5, "e": 2, "w": "gun"}]
    clip.build_ass(words, {"start": 0, "end": 10, "hook": "He lost it", "creator": "sykkuno"}, ass)
    txt = ass.read_text()
    assert ",Cap," not in txt and ",Hook," in txt and ",Mark," in txt
    clip.build_ass(words, {"start": 0, "end": 10, "hook": "He lost it", "creator": "xqc"}, ass)
    assert ",Cap," in ass.read_text()


def test_caption_keyword_skips_filler():
    assert clip._key_index(["bro", "what"]) is None
    assert clip._key_index(["just", "ZOOM!"]) == 1


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

    ass, with_ctx = make("with", base)
    _, no_ctx = make("without", {**base, "hook": ""})
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                "csv=p=0", str(with_ctx)], capture_output=True, text=True, check=True).stdout)
    assert 59 <= dur <= 60.5
    assert "HE LOST" in ass.read_text()
    w, h = (int(v) for v in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=width,height", "-of", "csv=p=0", str(with_ctx)], capture_output=True, text=True,
            check=True).stdout.strip().split(","))
    assert (w, h) == (1080, 1920)

    def frame(mp4):
        return subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", "1", "-i", str(mp4), "-frames:v", "1",
                               "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    assert frame(with_ctx) != frame(no_ctx)  # hook is actually drawn


def test_draft_pick_passes_clip_id_to_writer(tmp_path, monkeypatch):
    import writer
    (tmp_path / "transcript.txt").write_text("[1.0-4.0] hello there")
    seen = {}

    def fake(win, creator, meta=None, clip_id=None):
        seen["clip_id"] = clip_id
        return {**PLAN, "in": 0.0, "out": 10.0}
    monkeypatch.setattr(writer, "write_clip", fake)
    clip.draft_pick(tmp_path, {"start": 0.0, "end": 10.0}, "Kai Cenat", {}, clip_id=42)
    assert seen["clip_id"] == 42


def test_market_window_keeps_the_length_viewers_chose():
    # VM pass 2026-10-19: Writer said 0.0-3.4 inside a 16.7 s clip and 0.5-6.7 inside 37.1 s.
    assert clip.market_window({"start": 0.0, "end": 16.7}, 0.0, 3.4) == (0.0, 14.7)
    assert clip.market_window({"start": 0.0, "end": 37.1}, 0.5, 6.7) == (0.5, 35.1)


def test_market_window_allows_small_dead_air_trims_and_clamps_outside():
    assert clip.market_window({"start": 10.0, "end": 40.0}, 11.5, 39.0) == (11.5, 39.0)   # within 2 s
    assert clip.market_window({"start": 10.0, "end": 40.0}, 5.0, 50.0) == (10.0, 40.0)   # never outside
    assert clip.market_window({"start": 10.0, "end": 40.0}, 20.0, 30.0) == (12.0, 38.0)  # max 2 s each end


def test_market_window_short_pick_never_inverts():
    assert clip.market_window({"start": 0.0, "end": 3.0}, 2.5, 0.5) == (0.0, 3.0)


def test_market_meta_gives_the_writer_todays_popping_titles(tmp_path, monkeypatch):
    m = tmp_path / "market.json"
    m.write_text(json.dumps({"updated": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                             .strftime("%Y-%m-%dT%H:%M:%SZ"), "window_h": 48, "streamers": {"CaseOh": {"shorts": [
                                 {"title": "Someone needs to lock CaseOh up 😭🙏", "vph": 6869, "dur": 16, "en": True}]}}}))
    monkeypatch.setenv("CLIPPER_MARKET", str(m))
    name, titles = clip.market_meta("caseoh_")
    assert name == "CaseOh" and titles[0]["title"].startswith("Someone needs")
    monkeypatch.setenv("CLIPPER_MARKET", str(tmp_path / "none.json"))
    assert clip.market_meta("caseoh_") == ("CaseOh", [])              # name fix works without a scan
    assert clip.market_meta("somebody") == ("somebody", [])


def test_length_follows_the_top_clippers():
    pick = {"start": 0, "end": 58}
    assert clip.length_window(pick, 30, 52, 22) == (30, 52)                  # Writer's best 22 s part
    assert clip.length_window(pick, 0, 58, 22) == (36, 58)                   # ignored the target -> last 22 s
    assert clip.length_window(pick, 50, 80, 22) == (36, 58)                  # outside the window -> last 22 s
    assert clip.length_window({"start": 0, "end": 15}, 0, 15, 22) == (0, 15)  # never longer than the window


def test_same_moment_title_and_length_follow_that_clippers_short(tmp_path, monkeypatch):
    import writer
    (tmp_path / "transcript.txt").write_text("\n".join(f"[{t}.0-{t + 2}.0] words" for t in range(0, 58, 2)))
    monkeypatch.setattr(clip, "market_meta", lambda c: ("Jynxzi", [{"title": "Other popping title", "vph": 5, "dur": 30}]))
    monkeypatch.setattr(clip, "market_length", lambda c: 30)
    seen = {}

    def fake(win, creator, meta=None, clip_id=None):
        seen.update(meta)
        return {**PLAN, "title": "Jynxzi's mom catches him live", "in": 30.0, "out": 52.0}
    monkeypatch.setattr(writer, "write_clip", fake)
    same = {"title": "Jynxzi's Mom Walks In On Stream 😭", "dur": 22, "vph": 9000}
    p = clip.draft_pick(tmp_path, {"start": 0.0, "end": 58.0}, "jynxzi", {}, same=same)
    assert seen["same_moment"] == {"title": same["title"], "dur": 22}
    assert [x["title"] for x in seen["popping_now"]] == [same["title"], "Other popping title"]  # copy guard covers it
    assert seen["target_len_s"] == 22 and (p["start"], p["end"]) == (30.0, 52.0)               # their length


def test_same_moment_lookup_needs_a_db_and_a_match(tmp_path):
    import sqlite3
    assert clip.same_moment(None, "c1") is None
    con = sqlite3.connect(":memory:")
    assert clip.same_moment(con, "c1") is None                      # no table yet: no crash
    con.execute("CREATE TABLE moment_matches (short_id, streamer, clip_id, confidence, short_title, short_vph,"
                " short_dur, candidate_json, matched_at, layout)")
    con.execute("INSERT INTO moment_matches VALUES ('s', 'Jynxzi', 'c1', 0.9, 'T', 900, 21, '{}', '2026-10-20 10:00:00',"
                " 'stack')")
    assert clip.same_moment(con, "c1") == {"title": "T", "dur": 21, "vph": 900, "layout": "stack"}


def test_own_captions_are_cut_away_in_crop_mode_and_ours_go_on(tmp_path, monkeypatch):
    # Stable Ronaldo 2026-10-21: his own captions were half cut by the 9:16 crop and we drew none
    monkeypatch.setattr(clip, "own_caption_logins", lambda *a, **k: {"stableronaldo"})
    ron = {"start": 0, "end": 10, "hook": "He lost it", "creator": "stableronaldo"}
    assert not clip.draws_captions({**ron, "layout": {"mode": "stack"}})
    assert clip.draws_captions({**ron, "layout": {"mode": "crop", "cut": 0.14}})
    assert clip.draws_captions({**ron, "layout": {"mode": "stack", "cut": 0.14}})       # Jynxzi: his sat under the UI
    assert clip.draws_captions({**ron, "creator": "xqc", "layout": {"mode": "stack"}})
    seen = {}
    import layout
    monkeypatch.setattr(layout, "detect_layout", lambda v, s, e, cut=0.0, prefer=None: seen.setdefault("cut", cut) and
                        {"mode": "crop", "cx": 1, "W": 2, "H": 2, "cut": cut})
    assert clip.ensure_layout("v.mp4", ron)["layout"]["cut"] == layout.OWN_CAPTION_CUT
    words = [{"s": 1, "e": 1.5, "w": "my"}, {"s": 1.5, "e": 2, "w": "gun"}]
    ass, mp4 = tmp_path / "a.ass", tmp_path / "a.mp4"
    clip.build_ass(words, {**ron, "layout": {"mode": "crop", "cut": 0.14}}, ass)
    assert ",Cap," in ass.read_text()
    clip.write_render_info(mp4, {"layout": {"mode": "crop", "cut": 0.14, "path": [[0, 1], [1, 2]]}}, ass)
    assert json.loads(clip.render_info_path(mp4).read_text()) == {"our_captions": True, "mode": "crop",
                                                                   "cut": 0.14, "moving": True}


def test_captions_stop_at_sentence_ends_and_drop_full_stops():
    # fry clip 2026-10-21: "TWO. WHAT", "LEMONADE. I" (two sentences in one caption, with the full stop)
    ws = [{"s": i, "e": i + 0.5, "w": w} for i, w in enumerate(["One", "two.", "What", "is", "it?", "Lemonade,", "I"])]
    assert [[w["w"] for w in g] for g in clip.caption_chunks(ws, 2)] == [["One", "two."], ["What", "is"], ["it?"],
                                                                          ["Lemonade,", "I"]]
    assert [clip.bare(t) for t in ["two.", "it?", "Lemonade,", "U.S.", "wait...", "\"no.\""]] == \
        ["two", "it?", "Lemonade", "U.S", "wait", "\"no\""]
    assert "TWO" in clip.caption_text(["two."]) and "." not in clip.caption_text(["two."]).split("}")[-1]


def test_chatstack_keeps_our_text_above_the_chat_panel(tmp_path):
    ass = tmp_path / "a.ass"
    words = [{"s": 1, "e": 1.5, "w": "my"}, {"s": 1.5, "e": 2, "w": "gun"}]
    lay = {"mode": "chatstack", "chat_h": 640, "cx": 1, "W": 2, "H": 2}       # picture ends at 1280
    clip.build_ass(words, {"start": 0, "end": 10, "hook": "He lost it", "creator": "xqc", "layout": lay}, ass,
                   st={**__import__("style").DEFAULT, "position": "lower"})
    txt = ass.read_text()
    assert "\\pos(540,1140)" in txt and "\\pos(540,1230)" in txt          # captions and handle above it


def test_layout_hint_copies_the_matched_clipper_then_the_market(monkeypatch):
    import style
    monkeypatch.setattr(clip, "same_moment", lambda con, cid: {"title": "t", "layout": "fit"} if cid == "m" else None)
    monkeypatch.setattr(style, "market_layout", lambda creator, sp=None: "full")
    assert clip.layout_hint(None, "m", "stableronaldo") == "fit"           # that exact moment's clipper
    assert clip.layout_hint(None, "x", "stableronaldo") == "full"          # how the market frames him
