"""#124: some clippers size each word on its own and pop captions in differently: per word size from their letter
heights, per caption reveal when it differs from the Short's usual one. Offline: synthetic frames."""
import sys
from pathlib import Path

import cv2
import numpy as np

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER)]
from remake import caps, style  # noqa: E402


def frame_with(words):
    """words: [(text, x, font scale)] on one line at y=330 of a 360x640 frame, white with a black outline."""
    rng = np.random.default_rng(3)
    base = cv2.GaussianBlur(rng.integers(40, 200, (640, 360, 3), dtype=np.uint8), (0, 0), 6)
    th = base.copy()
    for text, x, sc in words:
        m = np.zeros(th.shape[:2], np.uint8)
        cv2.putText(m, text, (x, 340), cv2.FONT_HERSHEY_DUPLEX, sc, 255, max(2, int(3 * sc)), cv2.LINE_8)
        th[cv2.dilate(m, np.ones((7, 7), np.uint8)) > 0] = (0, 0, 0)
        th[m > 0] = (255, 255, 255)
    return base, th


def ev(*words):
    return {"start": 0, "end": 1, "y": 0.52, "lines": [len(words)], "words": [{"w": w, "c": "#FFFFFF", "t": 0} for w in words]}


def test_a_big_word_next_to_normal_ones_is_measured_bigger():
    base, th = frame_with([("SAY", 20, 0.9), ("WHAT", 105, 1.8)])
    m = style.measure_event(th, base, ev("SAY", "WHAT"))
    assert m and m["heights"][0] and m["heights"][1]
    assert 1.6 < m["heights"][1] / m["heights"][0] < 2.4
    assert m["lines"][0]["w0"] == 0 and m["lines"][0]["w1"] == 2


def test_word_sizes_are_relative_to_their_normal_words_and_skip_lower_case():
    evs = [ev("ONE", "TWO"), ev("THREE", "FOUR"), ev("SO", "BIG"), ev("tiny", "Word"), ev("ODD", "SPLIT"),
           ev("A", "BIT", "TALLER")]
    ms = [{"heights": [40, 41]}, {"heights": [39, 40]}, {"heights": [40, 80]}, {"heights": [20, 60]},
          {"heights": [6, 134]}, {"heights": [40, 46, 48]}]
    sizes = style.word_sizes(evs, ms)
    assert sizes[0] is None and sizes[1] is None                  # normal captions: one size
    assert sizes[2] == [1.0, 2.0]                                 # the big word, sized on its own
    assert sizes[3] is None                                       # lower case: letter heights mean nothing
    assert sizes[4] is None                                       # 6 px / 134 px "words": a mis-split line
    assert sizes[5] is None                                       # 15 % off is measuring noise, not a size


def test_a_height_the_frames_disagree_on_is_not_used():
    assert style.steady([40, 41, 40]) == 40
    assert style.steady([30, 40, 41]) is None                     # still popping in on one frame
    assert style.steady([None, 44]) == 44 and style.steady([]) is None


def test_reveals_read_from_letter_heights_and_brightness():
    pop = style.reveal_of([0, 30, 36, 44, 41, 40, 40, 40, 40, 40], [0] + [250] * 9, 60)
    assert pop["kind"] == "pop" and pop["from"] < 0.8 and pop["peak"] > 1.05
    fade = style.reveal_of([0] + [40] * 9, [0, 80, 150, 220, 250, 250, 250, 250, 250, 250], 60)
    assert fade["kind"] == "fade" and fade["ms"] > 30
    assert style.reveal_of([0] + [40] * 9, [0] + [250] * 9, 60)["kind"] == "none"
    assert style.reveal_of([0, 0, 0], [0, 0, 0], 60) is None
    assert style.same_reveal(pop, {**pop, "from": pop["from"] + 0.05}) and not style.same_reveal(pop, fade)


def test_ass_writes_each_words_size_and_each_captions_own_reveal(tmp_path):
    st = {"family": "Anton", "bold": 0, "italic": 0, "fs": 80.0, "spacing": 0, "outline": 4.0, "line_h": 60,
          "x": 0.5, "y": 0.5, "anim": {"kind": "none", "ms": 0}, "llm": {"case": "upper"},
          "sizes": [None, [1.0, 2.0]], "anims": [None, {"kind": "pop", "from": 0.6, "peak": 1.1, "t_peak_ms": 50,
                                                       "ms": 120}]}
    evs = [ev("NORMAL", "WORDS"), {**ev("SO", "BIG"), "start": 1.0, "end": 2.0}]
    for e in evs[1:]:
        for w in e["words"]:
            w["t"] = 1.0
    txt = Path(caps.write_ass_style(evs, tmp_path / "c.ass", 1080, 1920, st)).read_text()
    main = [ln for ln in txt.splitlines() if ln.startswith("Dialogue: 2,")]
    assert "\\fs" not in main[0] and "fscx60" not in main[0]           # first caption: their usual look
    assert "\\fs160.0" in main[1] and main[1].count("\\fs1") == 1      # BIG at twice the size, SO normal
    assert "\\fscx60\\fscy60" in main[1]                              # its own pop
