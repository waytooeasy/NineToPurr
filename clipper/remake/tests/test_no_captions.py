"""A clipper that adds no captions: the text on screen is the stream's own, so we add none (2026-10-28)."""
import json

from remake import caps, match, run

EV = [{"t0": 1.0, "t1": 2.0, "y": 0.7, "words": [{"w": "Right", "t": 1.0}, {"w": "to", "t": 1.2}, {"w": "jail.", "t": 1.4}]}]


def setup(tmp_path, monkeypatch, theirs_have_captions):
    (tmp_path / "base.mp4").write_bytes(b"BASE")
    (tmp_path / "pixcaps.json").write_text(json.dumps({"events": EV}))
    (tmp_path / "style.json").write_text(json.dumps({"ok": False}))
    monkeypatch.setattr(caps, "write_ass", lambda *a, **k: None)
    monkeypatch.setattr(match, "burn", lambda base, ass, out: (out.write_bytes(b"CAPS"), out)[1])

    def score(short, cand, *a, **k):
        no_caps = cand.read_bytes() == b"BASE"
        good = no_caps != theirs_have_captions
        return {"picture": 96.0, "captions": 85.0 if good else 24.0, "overall": 0, "per_frame": [], "bad": []}
    monkeypatch.setattr(match, "score", score)
    vm = {"out_w": 1080, "out_h": 1920, "fps": 30, "nfr": 900}
    return run.build_best(tmp_path / "short.mp4", tmp_path, vm, {}, {}, {"events": EV}, {"dur": 30.0}, None)


def test_text_that_is_in_the_stream_gets_no_captions_on_top(tmp_path, monkeypatch):
    best = setup(tmp_path, monkeypatch, theirs_have_captions=False)
    assert best["name"] == run.NO_CAPTIONS and best["match"]["captions"] == 85.0
    assert best["path"].read_bytes() == b"BASE" and (tmp_path / "base.mp4").exists()


def test_their_own_captions_still_get_ours(tmp_path, monkeypatch):
    best = setup(tmp_path, monkeypatch, theirs_have_captions=True)
    assert best["name"] != run.NO_CAPTIONS and best["match"]["captions"] == 85.0
    assert best["name"] == "study look"
    assert [t["captions"] for t in best["tried"]][-1] == 24.0               # none: their captions are missing
