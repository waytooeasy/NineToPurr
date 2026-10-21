"""Remake engine (D58): audio map, video map maths, framing, look, captions, title, picking and registering.
Offline: synthetic audio/images, fake model calls, in-memory DB with every migration."""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER)]
from remake import amap, caps, render, run, source, title, vmap  # noqa: E402

DB = CLIPPER / "db"
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript((DB / "schema.sql").read_text())
    c.executescript((DB / "ledger.sql").read_text())
    for f in sorted((DB / "migrations").glob("*.sql")):
        c.executescript(f.read_text())
    return c


# ---------------- audio map ----------------
def test_audio_map_finds_each_piece_its_offset_gain_and_switch():
    sr = 8000
    rng = np.random.default_rng(1)
    stream = (rng.standard_normal(60 * sr) * 0.1).astype(np.float32)
    stream = np.convolve(stream, np.ones(3) / 3, "same").astype(np.float32)
    pieces = [(10.0, 14.0, 1.0), (30.0, 33.0, 2.0), (40.0, 45.0, 1.0)]   # stream seconds, gain
    short = np.concatenate([stream[int(a * sr):int(b * sr)] * g for a, b, g in pieces])
    rows = amap.dense(short, [stream], sr=sr)
    segs = amap.segments(rows, len(short) / sr)
    assert [round(s["off"]) for s in segs] == [10, 26, 33]
    amap.refine(short, [stream], segs, sr=sr)
    amap.switches(short, [stream], segs, sr=sr)
    assert [round(s["off"], 3) for s in segs] == [10.0, 26.0, 33.0]
    assert abs(segs[1]["gain"] - 2.0) < 0.05
    assert abs(segs[0]["t1"] - 4.0) < 0.01 and abs(segs[1]["t1"] - 7.0) < 0.01


def test_sections_cover_every_offset_and_split_far_ones():
    secs = source.sections_for([100.0, 130.0, 900.0], dur=30, pad=20)
    assert secs == [(80.0, 180.0), (880.0, 950.0)]


def test_short_download_uses_the_cookie_file_only_when_present(tmp_path, monkeypatch):
    seen = []

    class OK:
        returncode, stderr = 0, ""

    def runner(cmd, **k):
        seen.append(cmd)
        return OK()
    monkeypatch.setenv("YTDLP_COOKIES", str(tmp_path / "missing.txt"))
    (tmp_path / "a").mkdir()
    source.download_short("a", tmp_path / "a", runner=runner)
    assert "--cookies" not in seen[-1]
    c = tmp_path / "cookies.txt"
    c.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("YTDLP_COOKIES", str(c))
    (tmp_path / "b").mkdir()
    source.download_short("b", tmp_path / "b", runner=runner)
    assert seen[-1][seen[-1].index("--cookies") + 1] == str(c)


def test_bot_check_is_reported_not_worked_around(tmp_path):
    class R:
        returncode, stderr = 1, "ERROR: [youtube] x: Sign in to confirm you're not a bot. Use --cookies"
    with pytest.raises(source.BotCheck):
        source.download_short("x", tmp_path, runner=lambda *a, **k: R())


# ---------------- video map ----------------
def texture(w=960, h=540, seed=3):
    rng = np.random.default_rng(seed)
    img = np.full((h, w), 120, np.uint8)
    for _ in range(400):
        x, y, r = int(rng.integers(0, w)), int(rng.integers(0, h)), int(rng.integers(4, 30))
        cv2.circle(img, (x, y), r, int(rng.integers(0, 255)), -1)
        cv2.rectangle(img, (x, y), (x + r, y + r // 2), int(rng.integers(0, 255)), 2)
    return img


def test_similarity_recovers_their_crop():
    sec = texture()
    # their 540x720 frame shows stream rect x 300..600, y 50..450 (k = 300/540 stream px per their px)
    k = 300 / 540
    M = np.array([[k, 0, 300], [0, k, 50]])
    their = cv2.warpAffine(sec, M, (540, 720), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    got = vmap.similarity(vmap._feats(their), vmap._feats(sec))
    assert got is not None
    assert abs(got[0, 0] - k) < 0.01 and abs(got[0, 2] - 300) < 2 and abs(got[1, 2] - 50) < 2
    assert vmap.warp_ncc(their, sec, got) > 0.95


def test_to_out_converts_analysis_map_to_output_frame():
    # their 2160x2880, section 1920x1080; analysis map: their(540 wide) -> section(960 wide)
    M = [[0.75, 0, 200], [0, 0.75, 10]]
    k, cx, cy, rot = vmap.to_out(M, (2160, 2880), (1920, 1080), out_w=1080)
    assert abs(k - 2 * 0.75 * 540 / 1080) < 1e-9          # section px per output px
    assert abs(cx - 2 * (0.75 * 270 + 200)) < 1e-9 and abs(cy - 2 * (0.75 * 360 + 10)) < 1e-9 and rot == 0


def test_shots_split_on_jumps_and_drop_one_frame_glitches():
    f = [{"n": n, "seg": 0, "k": 0.73, "cx": 900 + n, "cy": 540} for n in range(20)]     # a slow pan
    f[10] = {**f[10], "cx": 1300}                                                        # one bad match
    f += [{"n": n, "seg": 1, "k": 0.73, "cx": 500, "cy": 540} for n in range(20, 40)]     # cut: new seconds
    f += [{"n": n, "seg": 1, "k": 0.60, "cx": 500, "cy": 540} for n in range(40, 50)]     # punch-in, same seconds
    shots = vmap.split_shots(f, (1920, 1080))
    assert [s[0]["n"] for s in shots] == [0, 20, 40]
    assert all(x["n"] != 10 for x in shots[0])


def test_layout_full_vs_fit():
    assert vmap.layout_of(0.7277, 960, 540, (1080, 1440), (1920, 1080))[0] == "full"
    lay, band = vmap.layout_of(1.458, 993, 540, (1080, 1440), (1920, 1080))
    assert lay == "fit" and abs(band[0] - 0.243) < 0.01 and abs(band[1] - 0.757) < 0.01


def test_smooth_keeps_holds_and_linear_pans():
    p = np.array([[0.0, 100.0 + 3 * i, 540.0] for i in range(30)])
    p[7, 1] += 40                                     # jitter spike
    s = vmap.smooth(p)
    assert np.allclose(s[14:24, 1], 100 + 3 * np.arange(14, 24), atol=0.5)   # a spike moves a median one step nearby
    assert np.allclose(s[:, 2], 540)


# ---------------- framing + look ----------------
def vm_one(layout, k, cx, cy, bg=None):
    shot = {"n0": 0, "n1": 10, "seg": 0, "sec": 0, "off": 0.0, "layout": layout,
            "path": {str(n): [k, cx, cy] for n in range(10)}, **({"bg": bg} if bg else {})}
    return {"out_w": 1080, "out_h": 1440, "fps": 60, "nfr": 10, "shots": [shot], "frames": {},
            "sections": [{"file": "x", "fps": 60, "w": 1920, "h": 1080}]}, shot


def test_compose_full_crop_matches_the_map():
    sec = cv2.cvtColor(cv2.resize(texture(), (1920, 1080)), cv2.COLOR_GRAY2BGR)
    vm, shot = vm_one("full", 0.7277, 1000, 540)
    out = render.compose(sec, vm, shot, 0)
    assert out.shape == (1440, 1080, 3)
    # output centre = stream (1000, 540)
    assert np.abs(out[720, 540].astype(int) - sec[540, 1000].astype(int)).max() <= 20
    half = render.compose(cv2.resize(sec, (960, 540)), vm, shot, 0, (540, 720))   # smaller render, same framing
    assert np.abs(half[360, 270].astype(int) - sec[540, 1000].astype(int)).max() <= 30


def test_compose_fit_puts_the_stream_in_a_band_over_blur():
    sec = np.zeros((1080, 1920, 3), np.uint8)
    sec[:, :] = (40, 200, 40)
    sec[500:580, 900:1020] = (255, 255, 255)
    vm, shot = vm_one("fit", 1.458, 960, 540, {"rel": 0.97, "sigma": 20, "gain": 0.5})
    out = render.compose(sec, vm, shot, 0)
    top = int(720 - 540 / 1.458)
    assert out[top + 10, 540, 1] > 190                    # inside the band: the stream itself
    assert out[top - 40, 540, 1] < 120                    # above it: the darker (gain 0.5) blurred copy


def test_grade_poly_identity_and_lut():
    W = np.zeros((20, 3))
    W[1:4] = np.eye(3)[[0, 1, 2]] if False else 0
    rng = np.random.default_rng(0)
    X = rng.random((5000, 3))
    F = render.poly_feats(X)
    W, *_ = np.linalg.lstsq(F, X, rcond=None)
    lut = render.lut128(W)
    img = rng.integers(0, 256, (20, 20, 3), dtype=np.uint8)
    out = render.apply_look(img, lut)
    assert np.abs(out.astype(int) - img.astype(int)).max() <= 2
    flash = render.apply_overlay(img, 0.5, (0, 0, 255))
    assert flash[..., 2].mean() > img[..., 2].mean()


def test_audio_build_crossfades_and_gains(tmp_path):
    sr = 8000
    t = np.arange(20 * sr) / sr
    tone = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    wav = tmp_path / "sec.wav"
    render.write_wav(wav, np.stack([tone, tone], 1), sr)
    am = {"segments": [{"sec": 0, "off": 5.0, "t0": 0, "t1": 1.0, "gain": 1.0},
                       {"sec": 0, "off": 10.0, "t0": 1.0, "t1": 2.0, "gain": 2.0}], "booms": []}
    a = render.build_audio(am, [{"file": str(wav)}], 2.0, sr=sr)
    assert a.shape == (2 * sr, 2)
    r1 = np.sqrt(np.mean(a[int(0.2 * sr):int(0.8 * sr), 0] ** 2))
    r2 = np.sqrt(np.mean(a[int(1.2 * sr):int(1.8 * sr), 0] ** 2))
    assert 1.6 < r2 / r1 < 2.1                           # +6 dB on the second piece (tanh-limited)


# ---------------- captions ----------------
def rows_for(seq):
    """seq: [(t, [[(word, colour), ...], ...])]."""
    return [{"t": t, "lines": lines, "y": 0.5} for t, lines in seq]


def test_caption_events_reveal_words_and_split_captions():
    R_, W_ = "#E8201E", "#FFFFFF"
    rows = rows_for([(0.0, []), (0.1, [[("*STEALS", R_)]]), (0.2, [[("*STEALS", R_), ("FR", R_)]]),
                     (0.3, [[("*STEALS", R_), ("FRIES*", R_)]]), (0.4, [[("*STEALS", R_), ("FRIES*", "#E0201C")]]),
                     (0.5, []), (0.6, [[("TO", W_), ("THE", W_)], [("PATCH?", "#FF5050")]]),
                     (0.7, [[("TO", W_), ("THE", W_)], [("PATCH?", "#FF5050")]]), (0.8, [])])
    evs = caps.events(rows)
    assert len(evs) == 2
    a, b = evs
    assert [w["w"] for w in a["words"]] == ["*STEALS", "FRIES*"]
    assert a["words"][0]["t"] == pytest.approx(0.05) and a["words"][1]["t"] == pytest.approx(0.15)
    assert a["words"][1]["c"].startswith("#E")             # colour is the median of what was read
    assert b["lines"] == [2, 1] and b["words"][0]["c"] == "#FFFFFF"


def test_continued_caption_is_one_event():
    W_ = "#FFFFFF"
    evs = [{"start": 21.45, "end": 21.85, "y": 0.5, "lines": [3], "words": [
               {"w": "I", "c": W_, "t": 21.45}, {"w": "GOT", "c": W_, "t": 21.45}, {"w": "YOU", "c": W_, "t": 21.65}]},
           {"start": 21.85, "end": 22.75, "y": 0.5, "lines": [4, 1], "words": [
               {"w": "I", "c": W_, "t": 21.85}, {"w": "GOT", "c": W_, "t": 21.85}, {"w": "YOU", "c": W_, "t": 21.85},
               {"w": "YOUR", "c": W_, "t": 21.85}, {"w": "FLOWERS", "c": "#7CFC6A", "t": 21.95}]},
           {"start": 24.8, "end": 26.0, "y": 0.5, "lines": [1], "words": [{"w": "ALRIGHT", "c": W_, "t": 24.8}]}]
    out = caps.merge_continuations(evs)
    assert len(out) == 2 and [w["w"] for w in out[0]["words"]][-1] == "FLOWERS"
    assert out[0]["words"][2]["t"] == 21.65 and out[0]["end"] == 22.75 and out[0]["lines"] == [4, 1]


def test_ass_has_layers_reveals_line_breaks_and_handle(tmp_path):
    ev = {"start": 1.0, "end": 2.0, "y": 0.5, "lines": [2, 1],
          "words": [{"w": "TO", "c": "#FFFFFF", "t": 1.0}, {"w": "THE", "c": "#FFFFFF", "t": 1.2},
                    {"w": "PATCH?", "c": "#FF5050", "t": 1.5}]}
    p = caps.write_ass([ev], tmp_path / "c.ass", 1080, 1440, fs=89.4, fsp=10.6, mark="@Peakz.Recaps", dur=10)
    text = Path(p).read_text()
    assert text.count("Dialogue: ") == 4                    # shadow, glow, fill + our handle
    assert "\\t(500,630," in text and "\\N" in text and "&H5050FF&" in text
    assert "Montserrat Black,89.4" in text and "@Peakz.Recaps" in text


def test_ocr_parse_needs_one_object_per_frame():
    assert caps.parse('```json\n[{"lines": [], "y": null}]\n```', 1) == [{"lines": [], "y": None}]
    assert caps.parse("[{}]", 2) is None and caps.parse("no json", 1) is None


# ---------------- title ----------------
def test_title_is_ours_never_theirs():
    theirs = "Jason And Ron Goes On A Date 💕😂"
    answers = iter(["Jason and Ron Goes On A Date 💕😂", "Ron Takes Jason On A Fry Date 😂"])
    t = title.make(theirs, "Stable Ronaldo", "STEALS FRIES", ask=lambda p: next(answers))
    assert t == "Ron Takes Jason On A Fry Date 😂" and not title.too_close(t, theirs)
    assert title.clean('"Hello #fyp"\nmore') == "Hello"


# ---------------- picking + registering ----------------
MARKET = {"streamers": {
    "Stable Ronaldo": {"shorts": [
        {"id": "A", "title": "a", "channel": "SpecificMinds", "views": 30000, "vph": 9000, "dur": 29,
         "published": "2026-10-21T05:00:00Z", "en": True},
        {"id": "OLD", "title": "o", "channel": "x", "views": 9e5, "vph": 20000, "dur": 30,
         "published": "2026-10-18T05:00:00Z", "en": True},
        {"id": "LONG", "title": "l", "channel": "x", "views": 9e5, "vph": 20000, "dur": 95,
         "published": "2026-10-21T05:00:00Z", "en": True},
        {"id": "OURS", "title": "u", "channel": "Peakz Recaps", "views": 9e5, "vph": 20000, "dur": 30,
         "published": "2026-10-21T05:00:00Z", "en": True}]},
    "Jynxzi": {"shorts": [{"id": "B", "title": "b", "channel": "c", "views": 50000, "vph": 12000, "dur": 40,
                           "published": "2026-10-21T10:00:00Z", "en": True}]},
    "IShowSpeed": {"shorts": [{"id": "YT", "title": "s", "channel": "c", "views": 5e5, "vph": 90000, "dur": 40,
                               "published": "2026-10-21T10:00:00Z", "en": True}]}}}


def test_candidates_popping_recent_short_twitch_not_ours_not_tried():
    c = db()
    c.execute("INSERT INTO remakes (short_id, status) VALUES ('B', 'done')")
    got = run.candidates(MARKET, c, NOW, twitch_names={"Stable Ronaldo", "Jynxzi"})
    assert [s["id"] for s in got] == ["A"]
    c.execute("DELETE FROM remakes")
    got = run.candidates(MARKET, c, NOW, twitch_names={"Stable Ronaldo", "Jynxzi"})
    assert [s["id"] for s in got] == ["B", "A"]                       # most popping first


def test_register_makes_an_edited_clip_the_bot_can_show():
    c = db()
    s = {"id": "A", "title": "Jason And Ron Goes On A Date", "channel": "SpecificMinds", "views": 30000,
         "vph": 9000, "published": "2026-10-21T05:00:00Z", "streamer": "Stable Ronaldo"}
    found = {"vod_id": "2904593598", "login": "stableronaldo", "sections": [{"file": "f", "vod_s": 2714.0, "vod_e": 3009}]}
    am = {"segments": [{"sec": 0, "off": 20.69, "t0": 0, "t1": 29.3}]}
    vm = {"nfr": 1759, "fps": 60}
    cp = {"events": [{"words": [{"w": "*STEALS"}, {"w": "FRIES*"}]}]}
    clip_id = run.register(c, s, found, am, vm, cp, "/tmp/x.mp4", "Ron Takes Jason On A Fry Date")
    row = c.execute("SELECT state, title, hook_text, music_risk, end_s - start_s AS d FROM clips WHERE id=?",
                    (clip_id,)).fetchone()
    assert row["state"] == "edited" and row["title"] == "Ron Takes Jason On A Fry Date"
    assert row["hook_text"] == "*STEALS FRIES*" and row["music_risk"] == 0 and abs(row["d"] - 1759 / 60) < 1e-6
    rc = c.execute("SELECT creator, source, video_id, vod_offset FROM radar_candidates WHERE clips_id=?",
                   (clip_id,)).fetchone()
    assert tuple(rc) == ("stableronaldo", "remake", "2904593598", 2734)


def test_same_moment_from_another_clipper_is_not_remade_twice():
    c = db()
    c.execute("INSERT INTO remakes (short_id, status, vod_id, vod_s, vod_e) VALUES ('A','done','v',100,130)")
    assert run.same_moment_done(c, "v", 105, 135)
    assert not run.same_moment_done(c, "v", 300, 330) and not run.same_moment_done(c, "w", 105, 135)


def test_daily_cap_counts_done_remakes():
    c = db()
    for i in range(3):
        c.execute("INSERT INTO remakes (short_id, status, updated_at) VALUES (?, 'done', ?)",
                  (f"s{i}", (NOW - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")))
    assert run.done_today(c, NOW) == 3
