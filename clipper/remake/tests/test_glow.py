"""#125: glow and drop shadow around their captions, measured on the pixels (the SpecificMinds look: colour glow
+ dark drop shadow), and the letters kept apart from the glow. Offline: synthetic frames."""
import sys
from pathlib import Path

import cv2
import numpy as np

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER)]
from remake import style, tune  # noqa: E402


def glow_frame(glow=True, shadow=(6, 8), colour=(60, 60, 255)):
    rng = np.random.default_rng(4)
    base = cv2.GaussianBlur(rng.integers(50, 140, (640, 360, 3), dtype=np.uint8), (0, 0), 8).astype(np.float32)
    m = np.zeros((640, 360), np.uint8)
    cv2.putText(m, "RON", (60, 340), cv2.FONT_HERSHEY_DUPLEX, 2.2, 255, 7, cv2.LINE_AA)
    letters = m.astype(np.float32) / 255
    out = base.copy()
    if shadow:
        dx, dy = shadow
        sh = cv2.GaussianBlur(np.roll(np.roll(letters, dy, 0), dx, 1), (0, 0), 2)
        out = out * (1 - 0.7 * sh[..., None])
    if glow:
        g = np.clip(cv2.GaussianBlur(letters, (0, 0), 7) * 2.2, 0, 1)
        out = out * (1 - 0.8 * g[..., None]) + np.array(colour, np.float32) * 0.8 * g[..., None]
    out = out * (1 - letters[..., None]) + np.array(colour, np.float32) * letters[..., None]
    return base.astype(np.uint8), np.clip(out, 0, 255).astype(np.uint8), m > 127


def test_glow_in_the_words_colour_and_a_drop_shadow_are_measured():
    base, th, letters = glow_frame()
    _, fill, _ = style.caption_masks(th, base, 0.52)
    h = style.halo(th, base, fill, 44, 0)
    assert h["glow"] and h["glow"]["colour"] == "text" and 0.1 < h["glow"]["size"] < 1.0
    assert h["shadow"] and h["shadow"]["dx"] > 0 and h["shadow"]["dy"] > 0


def test_plain_letters_have_no_glow_and_no_shadow():
    base, th, _ = glow_frame(glow=False, shadow=None)
    _, fill, _ = style.caption_masks(th, base, 0.52)
    h = style.halo(th, base, fill, 44, 0)
    assert h["glow"] is None and h["shadow"] is None


def test_glow_pixels_are_not_counted_as_letters():
    base, th, letters = glow_frame(shadow=None, colour=(255, 255, 255))
    _, fill, _ = style.caption_masks(th, base, 0.52)
    tight = style.without_glow(th, fill, base)
    assert fill.sum() > 1.3 * letters.sum()                 # the glow made the letters look fat
    assert abs(int(tight.sum()) - int(letters.sum())) < 0.25 * letters.sum()


def test_measured_halo_beats_the_models_guess_and_needs_most_captions():
    guess = {"glow": {"present": True, "colour": "#FFFFFF", "size": 0.6, "opacity": 0.3}, "shadow": {"present": False}}
    hs = [{"glow": {"present": True, "size": 0.25, "colour": "text", "opacity": 0.7},
           "shadow": {"present": True, "dx": 0.1, "dy": 0.15, "opacity": 0.6, "colour": "#000000"}}] * 3 + \
         [{"glow": None, "shadow": None}]
    looks = style.merge_halos(hs, guess)
    assert looks["glow"]["size"] == 0.25 and looks["glow"]["colour"] == "text" and looks["glow"]["measured"]
    assert looks["shadow"]["present"] and looks["shadow"]["dy"] == 0.15
    none = style.merge_halos([{"glow": None, "shadow": None}] * 3, guess)
    assert none["glow"]["present"] is False                  # measured on 3 captions: no glow there


def test_tune_tries_glow_and_shadow_when_present():
    st = {"fs": 80.0, "track": 0.0, "dy": 0.0, "x": 0.5, "line_h": 60,
          "llm": {"glow": {"present": True, "size": 0.3, "opacity": 0.6}, "shadow": {"present": True, "dx": 0.1,
                                                                                      "dy": 0.1, "opacity": 0.5}}}
    seen = []

    def score(s):
        seen.append(s)
        g = s["llm"]["glow"]
        return abs(g["size"] - 0.42) + abs(s["llm"]["shadow"]["dy"] - 0.13)     # best: a bigger glow, lower shadow
    best, err = tune.tune(st, score)
    assert best["llm"]["glow"]["size"] > 0.3 and best["llm"]["shadow"]["dy"] > 0.1 and err < 0.15


def test_a_strong_glow_in_the_letters_own_colour_is_still_not_letter():
    rng = np.random.default_rng(4)
    base = cv2.GaussianBlur(rng.integers(50, 140, (640, 360, 3), dtype=np.uint8), (0, 0), 8).astype(np.float32)
    m = np.zeros((640, 360), np.uint8)
    cv2.putText(m, "RON", (60, 340), cv2.FONT_HERSHEY_DUPLEX, 2.2, 255, 7, cv2.LINE_AA)
    letters = m.astype(np.float32) / 255
    g = np.clip(cv2.GaussianBlur(letters, (0, 0), 6) * 3.0, 0, 1)          # ~95 % at the letters' edge
    out = base * (1 - 0.95 * g[..., None]) + np.array((40, 230, 255), np.float32) * 0.95 * g[..., None]
    out = out * (1 - letters[..., None]) + np.array((40, 230, 255), np.float32) * letters[..., None]
    th, base = np.clip(out, 0, 255).astype(np.uint8), base.astype(np.uint8)
    _, fill, _ = style.caption_masks(th, base, 0.52)
    tight = style.without_glow(th, fill, base)
    assert fill.sum() > 1.5 * (m > 127).sum()
    assert tight.sum() < 1.45 * (m > 127).sum() < 0.8 * fill.sum()
