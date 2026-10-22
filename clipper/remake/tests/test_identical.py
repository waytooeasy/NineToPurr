"""Identical remakes (Lucas 2026-10-21): their caption look measured from pixels, their per-frame colour effects,
and a match score against the original. Offline: synthetic frames and system fonts, ffmpeg for the short videos."""
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER)]
from remake import caps, look, match, render, style  # noqa: E402


def sysfont(pattern):
    try:
        p = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        return None
    return p if p and Path(p).exists() else None


def test_glyph_shapes_pick_the_font_their_captions_use(tmp_path):
    a, b = sysfont("DejaVu Sans:bold"), sysfont("DejaVu Serif:bold")
    if not a or not b or a == b:
        pytest.skip("system fonts not available")
    for p in (a, b):
        shutil.copy(p, tmp_path / Path(p).name)
    fonts = [("Sans", 1, 0, Path(a).name, ""), ("Serif", 1, 0, Path(b).name, "")]
    theirs = [(style.text_mask(tmp_path / Path(b).name, t, size=90, track=0.08), t) for t in ("JASON ASKS", "RON SAYS YES")]
    ranked = style.rank_fonts(theirs, fonts, tmp_path)
    assert ranked[0][1][0] == "Serif" and ranked[0][2] == 0.08 and ranked[0][0] > ranked[1][0] + 0.05


def _caption_frame(colours=((255, 255, 255), (0, 255, 255))):
    rng = np.random.default_rng(3)
    base = cv2.GaussianBlur(rng.integers(40, 200, (640, 360, 3), dtype=np.uint8), (0, 0), 6)
    th = base.copy()
    for (word, x), col in zip((("KAI", 50), ("CENAT", 150)), colours):
        m = np.zeros(th.shape[:2], np.uint8)
        cv2.putText(m, word, (x, 330), cv2.FONT_HERSHEY_DUPLEX, 1.4, 255, 4, cv2.LINE_8)
        th[cv2.dilate(m, np.ones((7, 7), np.uint8)) > 0] = (0, 0, 0)        # 3 px black outline
        th[m > 0] = col
    return base, th


def test_word_colours_position_and_outline_come_from_their_pixels():
    base, th = _caption_frame()
    ev = {"start": 0, "end": 1, "y": 0.5, "lines": [2],
          "words": [{"w": "KAI", "c": "#FF00FF", "t": 0}, {"w": "CENAT", "c": "#FF00FF", "t": 0}]}
    m = style.measure_event(th, base, ev)
    assert m["colours"][0] == "#FFFFFF"
    r, g, b = (int(m["colours"][1][i:i + 2], 16) for i in (1, 3, 5))
    assert r > 200 and g > 200 and b < 80            # yellow, not the OCR's magenta
    assert abs(m["cy"] - 320 / 640) < 0.03 and 0.4 < m["cx"] < 0.6
    assert m["outline"] >= 1.5 and len(m["lines"]) == 1


def test_no_caption_no_measure():
    base, _ = _caption_frame()
    assert style.measure_event(base.copy(), base, {"y": 0.5, "lines": [1], "words": [{"w": "X", "c": "#FFF", "t": 0}]}) is None


def test_per_frame_effects_black_and_white_and_flash_are_recovered():
    rng = np.random.default_rng(1)
    ours = rng.uniform(0, 255, (4000, 3))
    grey = ours @ np.array([[0.114] * 3, [0.587] * 3, [0.299] * 3])          # BGR -> grey in all channels
    M = look.frame_transform(ours, grey)
    assert M is not None
    out = render.apply_mat(ours.reshape(40, 100, 3).astype(np.uint8), M).astype(float)
    assert np.abs(out.reshape(-1, 3) - grey).mean() < 2
    red = ours * 0.5 + np.array([0, 0, 255]) * 0.5                          # red flash
    assert look.frame_transform(ours, red) is not None
    assert look.frame_transform(ours, ours + rng.normal(0, 2, ours.shape)) is None       # same frame: nothing
    assert look.frame_transform(ours, rng.uniform(0, 255, ours.shape)) is None          # wrong content: no fake fix


def test_measured_style_ass_has_their_font_size_colours_outline_and_pop(tmp_path):
    st = {"family": "Anton", "bold": 0, "italic": 0, "fs": 88.4, "spacing": 3.5, "outline": 5.0, "line_h": 70,
          "x": 0.5, "y": 0.62, "anim": {"kind": "pop", "from": 0.7, "peak": 1.12, "t_peak_ms": 60, "ms": 130},
          "colours": [["#FFFFFF", "#00FF00"]],
          "llm": {"outline": {"present": True, "colour": "#000000"}, "shadow": {"present": True, "dx": 0.05, "dy": 0.08,
                                                                                 "opacity": 0.7},
                  "glow": {"present": False}, "case": "upper"}}
    evs = [{"start": 0.5, "end": 1.5, "y": 0.5, "lines": [2],
            "words": [{"w": "yes", "c": "#FFFFFF", "t": 0.5}, {"w": "$80m", "c": "#FFFFFF", "t": 0.8}]}]
    txt = Path(caps.write_ass_style(evs, tmp_path / "c.ass", 1080, 1920, st, mark="@Peakz.Recaps", dur=3)).read_text()
    assert "Style: C,Anton,88.4," in txt and ",3.50,0,1,5.00,0," in txt
    main = [ln for ln in txt.splitlines() if ln.startswith("Dialogue: 2,")][0]
    assert "\\pos(540,1190)" in main and "YES" in main and "$80M" in main
    assert "\\c&H00FF00&" in main                        # green word, from their pixels
    assert "\\fscx70\\fscy70\\t(300,360,\\fscx112\\fscy112)\\t(360,430,\\fscx100\\fscy100)" in main
    assert any(ln.startswith("Dialogue: 1,") for ln in txt.splitlines())      # their drop shadow
    assert "@Peakz.Recaps" in txt


def test_fade_and_instant_reveals():
    assert caps._reveal(200, {"kind": "fade", "ms": 100}) == "\\alpha&HFF&\\t(200,300,\\alpha&H00&)"
    assert caps._reveal(0, {"kind": "none"}) == "\\alpha&HFF&\\t(0,1,\\alpha&H00&)"


def _video(path, frames, fps=30):
    h, w = frames[0].shape[:2]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)],
                         stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()
    return path


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg")
def test_match_score_sees_wrong_captions_and_wrong_pictures(tmp_path):
    rng = np.random.default_rng(5)
    bg = cv2.resize(rng.integers(0, 255, (12, 7, 3), dtype=np.uint8), (270, 480), interpolation=cv2.INTER_NEAREST)
    theirs, same, wrong_cap, wrong_pic = [], [], [], []
    for i in range(30):
        f = bg.copy()
        g = f.copy()
        cv2.putText(f, "YES", (80, 250), cv2.FONT_HERSHEY_DUPLEX, 1.5, (255, 255, 255), 4)
        theirs.append(f)
        same.append(f.copy())
        cv2.putText(g, "NO WAY", (40, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        wrong_cap.append(g)
        wrong_pic.append(f if i < 15 else 255 - f)
    T = _video(tmp_path / "t.mp4", theirs)
    Z = _video(tmp_path / "z.mp4", [bg] * 30)
    evs = [{"start": 0, "end": 1, "y": 0.5, "lines": [1], "words": [{"w": "YES", "c": "#FFFFFF", "t": 0}]}]
    ok = match.score(T, _video(tmp_path / "a.mp4", same), evs, 30, 30, 270, 480, base=Z)
    bad_cap = match.score(T, _video(tmp_path / "b.mp4", wrong_cap), evs, 30, 30, 270, 480, base=Z)
    bad_pic = match.score(T, _video(tmp_path / "c.mp4", wrong_pic), evs, 30, 30, 270, 480, base=Z)
    assert ok["picture"] == 100 and ok["captions"] == 100
    assert bad_cap["captions"] < 20 and bad_cap["picture"] == 100
    assert 40 <= bad_pic["picture"] <= 60 and bad_pic["bad"] and bad_pic["bad"][0][2] == "picture"


def test_caption_states_become_events_with_word_reveals():
    segs = [(0, 12), (12, 30), (30, 45), (50, 60), (90, 99)]
    texts = [[["YOU"]], [["YOU", "THINK"]], [["BOZO"]], [["BOZO"]], [["BOZO"]]]
    evs = style.state_events(segs, texts, 30, 0.5)
    # BOZO lost for 5 frames (a flash) is one caption; BOZO again a second later is a new one
    assert [(e["start"], e["end"]) for e in evs] == [(0.0, 1.0), (1.0, 2.0), (3.0, 3.3)]
    assert [(w["w"], w["t"]) for w in evs[0]["words"]] == [("YOU", 0.0), ("THINK", 0.4)]


def test_solid_box_padding_is_measured():
    th = np.full((400, 600, 3), 180, np.uint8)
    th[150:250, 100:500] = 5                     # their black box
    th[180:220, 140:460] = 255                   # the text inside it
    px, py = style.box_pad(th, (140, 460, 180, 220))
    assert abs(px - 40) <= 3 and abs(py - 30) <= 3
    assert style.box_pad(np.full((400, 600, 3), 180, np.uint8), (140, 460, 180, 220)) is None


def test_box_is_drawn_around_the_words_shown(tmp_path):
    st = {"family": "Anton", "fs": 150, "spacing": 0, "outline": 0, "line_h": 80, "x": 0.5, "y": 0.5, "dy": 10,
          "box_pad": [20, 18], "anim": {"kind": "none"}, "colours": [["#FFFFFF", "#FFFFFF"]],
          "llm": {"box": {"present": True, "colour": "#000000", "opacity": 1}}}
    evs = [{"start": 0, "end": 1, "lines": [2], "words": [{"w": "A", "c": "#FFFFFF", "t": 0},
                                                         {"w": "BB", "c": "#FFFFFF", "t": 0.5}]}]
    txt = Path(caps.write_ass_style(evs, tmp_path / "b.ass", 1080, 1920, st,
                                    width=lambda s: 50 * len(s))).read_text()
    boxes = [ln for ln in txt.splitlines() if "\\p1" in ln]
    assert len(boxes) == 2
    assert "m 495 902 l 585 902 585 1018 495 1018" in boxes[0]          # "A": 50 + 2*20 wide, 80 + 2*18 high
    assert "m 420 902 l 660 902" in boxes[1]                              # "A BB": 200 + 40 wide
    main = [ln for ln in txt.splitlines() if ln.startswith("Dialogue: 2,")][0]
    assert "\\pos(540,950)" in main                                      # letters' centre at y, minus libass offset


def test_video_is_resynced_when_the_audio_map_puts_it_a_frame_off():
    from remake import vmap
    rng = np.random.default_rng(2)
    sec = np.stack([cv2.GaussianBlur(rng.integers(0, 255, (120, 160), dtype=np.uint8), (0, 0), 2) for _ in range(30)])
    th = sec[1:21]                                   # their frame n is section frame n + 1
    M = [[1, 0, 0], [0, 1, 0]]
    out = [(n, 0, n, M, 0.9) for n in range(20)]     # the audio says section frame n
    fixed = vmap.resync(out, th, 0, sec, 0)
    assert [m for _, _, m, _, _ in fixed] == list(range(1, 21))
    assert vmap.resync(out, sec[:20], 0, sec, 0) == out


def test_alignment_recovers_their_framing_from_pixels():
    from remake import align
    rng = np.random.default_rng(4)
    sec = cv2.GaussianBlur(rng.integers(0, 255, (1080, 1920, 3), dtype=np.uint8), (0, 0), 4)
    vm = {"out_w": 1080, "out_h": 1920, "sections": [{"w": 1920, "h": 1080}]}
    true = {"layout": "full", "sec": 0, "path": {"0": [0.5, 960.0, 540.0]}}
    off = {"layout": "full", "sec": 0, "path": {"0": [0.505, 966.0, 535.0]}}      # a few px off, like a smoothed path
    W, h = align.W, int(round(align.W * 1920 / 1080 / 2) * 2)
    A = align._blank(align._gray(render.compose(sec, vm, true, 0, (W, h))), h)
    (k, cx, cy), _ = align.align_frame(A, sec, vm, off, 0, h)
    assert abs(k - 0.5) < 0.0015 and abs(cx - 960) < 1.5 and abs(cy - 540) < 1.5


def test_tuning_moves_the_caption_look_towards_theirs():
    from remake import tune
    evs = [{"start": 0, "end": 1, "y": 0.5, "lines": [2], "words": [{"w": "A", "c": "#FFFFFF", "t": 0},
                                                                  {"w": "B", "c": "#FFFFFF", "t": 0.9}]},
           {"start": 1.2, "end": 1.3, "y": 0.5, "lines": [1], "words": [{"w": "C", "c": "#FFFFFF", "t": 1.2}]}]
    ms = tune.moments(evs, 30)
    assert ms == [(0, 21, 1)]                         # 0.7 s in: only "A" is up; the 0.1 s caption is skipped
    sev, sst = tune.sample_events(evs, ms, {"colours": [["#FFFFFF", "#00FF00"]], "pos": [[0.4, 0.6]]})
    assert sev[0]["start"] == 0.5 and sev[0]["end"] == 1.5 and [w["w"] for w in sev[0]["words"]] == ["A"]
    assert sev[0]["lines"] == [1] and sst["colours"] == [["#FFFFFF"]] and sst["pos"] == [[0.4, 0.6]]
    target = {"fs": 106.0, "dy": 4.0, "x": 0.504}
    score = lambda s: abs(s["fs"] - target["fs"]) / 50 + abs(s["dy"] - target["dy"]) / 40 + abs(s["x"] - target["x"]) * 5  # noqa: E731
    best, err = tune.tune({"fs": 100.0, "track": 0.0, "spacing": 0.0, "dy": 0.0, "x": 0.5, "line_h": 60, "llm": {}},
                          score, rounds=2)
    assert abs(best["fs"] - 106) < 2 and abs(best["dy"] - 4) < 0.5 and abs(best["x"] - 0.504) < 1e-6 and err < 0.05


def test_a_clippers_caption_look_is_remembered_when_it_matched_better(tmp_path, monkeypatch):
    from remake import run
    monkeypatch.setenv("CLIPPER_REMAKE", str(tmp_path))
    st = {"family": "Antonio Bold", "fs": 134.0, "font_score": 0.76, "x": 0.5}
    run.save_channel_style("Succesful Celebrity", st, 85.0)
    assert run.load_channel_style("Succesful Celebrity")["family"] == "Antonio Bold"
    run.save_channel_style("Succesful Celebrity", {**st, "family": "Anton"}, 60.0)      # worse: not kept
    assert run.load_channel_style("Succesful Celebrity")["family"] == "Antonio Bold"
    assert "x" not in run.load_channel_style("Succesful Celebrity")                      # per Short, not per channel
    assert run.load_channel_style("") is None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg")
def test_a_render_one_frame_late_is_measured(tmp_path):
    rng = np.random.default_rng(9)
    frames = [cv2.resize(rng.integers(0, 255, (8, 5, 3), dtype=np.uint8), (270, 480), interpolation=cv2.INTER_NEAREST)
              for _ in range(60)]
    T = _video(tmp_path / "t.mp4", frames[1:59])
    late = _video(tmp_path / "o.mp4", frames[0:58])        # ours n + 1 shows their n
    assert match.frame_shift(T, late, step=3) == 1
    assert match.frame_shift(T, T, step=3) == 0


def test_states_carry_place_and_word_colours_and_ocr_highlights_win_over_a_white_pixel_read():
    segs = [{"n0": 0, "n1": 15, "box": [0.4, 0.6, 0.70, 0.76], "iou": [1.0] * 15}]
    evs = style.state_events(segs, [[[("RESPECT", "#FFE600")]]], 30, 0.5)
    assert evs[0]["x"] == 0.5 and evs[0]["y"] == 0.73 and evs[0]["words"][0]["c"] == "#FFE600"
    assert style.merge_colour("#FFFFFF", "#FFE600") == "#FFE600"
    assert style.merge_colour("#00FF00", "#FFFFFF") == "#00FF00"
    assert style.merge_colour(None, "#FFFFFF") == "#FFFFFF"


def test_a_long_state_read_twice_is_split_where_its_pixels_changed(tmp_path, monkeypatch):
    seg = {"n0": 0, "n1": 20, "box": None, "iou": [1.0] * 9 + [0.62] + [1.0] * 10}
    reads = iter([[[("YOU", "#FFFFFF"), ("KNOW", "#FFFFFF")]], [[("MONKEY", "#00FFFF")]]])
    monkeypatch.setattr(style, "ocr_frames", lambda *a, **k: [next(reads), next(reads)])
    segs, texts = style.read_states("x.mp4", [seg], 30, (1080, 1920), 0.5, None)
    assert [(s["n0"], s["n1"]) for s in segs] == [(0, 9), (9, 20)]
    assert texts[1][0][0][0] == "MONKEY"


def test_boxed_caption_is_found_away_from_the_usual_height():
    rng = np.random.default_rng(6)
    base = cv2.GaussianBlur(rng.integers(60, 200, (960, 540, 3), dtype=np.uint8), (0, 0), 5)
    th = base.copy()
    th[690:750, 150:390] = 5                           # their box, low in the frame
    cv2.putText(th, "RESPECT", (165, 735), cv2.FONT_HERSHEY_DUPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_8)
    rows, _ = style.text_lines(th, base, y=0.5, edged=True)
    assert rows and 690 <= rows[0][0] and rows[-1][1] <= 750


def test_ocr_answers_in_any_shape_are_read():
    assert style._parse_lines({"lines": [[["YOU", "#FFFFFF"], ["KNOW", "#00FFFF"]]]}) == [[("YOU", "#FFFFFF"), ("KNOW", "#00FFFF")]]
    assert style._parse_lines([[["HI", "#FFE600"]]]) == [[("HI", "#FFE600")]]
    assert style._parse_lines(["HELLO", "THERE"]) == [[("HELLO", "#FFFFFF"), ("THERE", "#FFFFFF")]]
    assert style._parse_lines({"lines": []}) == [] and style._parse_lines(None) == []
