import pytest

import writer as W

GOOD = {"score": 0.8, "in": 100.0, "out": 140.0,
        "hooks": ["He lost the bet", "Chat did this to Kai", "Kai regrets everything"],
        "context_line": "Kai lost a bet to chat and must eat spicy wings",
        "title": "Kai Cenat eats the spiciest wing after losing a bet",
        "music_risk": False}


def mock_llm(monkeypatch, plans):
    seen = []
    monkeypatch.setattr(W, "llm", lambda prompt, schema, **kw: seen.append(prompt) or dict(plans[len(seen) - 1]))
    return seen


def test_write_clip_ok_and_prompt_has_inputs(monkeypatch):
    seen = mock_llm(monkeypatch, [GOOD])
    out = W.write_clip("[100.0-110.0] hello chat", "Kai Cenat", {"views_per_hour": 900})
    assert out["in"] == 100.0 and len(out["hooks"]) == 3
    assert "Kai Cenat" in seen[0] and "hello chat" in seen[0] and "900" in seen[0]


def test_prompt_split_static_vs_per_clip(monkeypatch):
    system, user = W.load_prompt()
    assert "hook .30" in system and "{creator}" not in system and "{transcript}" in user
    got = {}
    monkeypatch.setattr(W, "llm", lambda prompt, schema, **kw: got.update(kw, prompt=prompt) or dict(GOOD))
    W.write_clip("[1-2] line", "Kai Cenat", clip_id=7)
    assert got["system"] == system and got["clip_id"] == 7
    assert "line" in got["prompt"] and "hook .30" not in got["prompt"]


def test_over_60s_gets_retry_then_ok(monkeypatch):
    seen = mock_llm(monkeypatch, [{**GOOD, "out": 200.0}, GOOD])
    assert W.write_clip("x", "Kai Cenat")["out"] == 140.0
    assert len(seen) == 2 and "60s" in seen[1]


def test_still_bad_raises(monkeypatch):
    mock_llm(monkeypatch, [{**GOOD, "out": 200.0}] * 2)
    with pytest.raises(ValueError):
        W.write_clip("x", "Kai Cenat")


@pytest.mark.parametrize("patch", [
    {"hooks": ["one two three four five six seven eight", "a", "b"]},
    {"context_line": "word " * 13},
    {"title": "A wild stream moment happened"},
])
def test_check_rejects(patch):
    with pytest.raises(ValueError):
        W.check({**GOOD, **patch}, "Kai Cenat")


def test_prompt_file_exists_and_formats():
    txt = W.PROMPT_FILE.read_text(encoding="utf-8")
    assert txt.format(creator="c", meta="{}", transcript="t")
    for w in ("hook", "coherence", "emotion", "value", "payoff", ".30"):
        assert w in txt


LIB = "# Format library\n## Hook templates\n1. `No way {person} came on stream ❤️‍🩹 #{S}`\n"


def test_market_library_goes_into_the_cached_system_part(tmp_path, monkeypatch):
    f = tmp_path / "library.md"
    f.write_text(LIB, encoding="utf-8")
    monkeypatch.setenv("CLIPPER_FORMATS", str(f))
    system, user = W.load_prompt()
    assert "TODAY'S MARKET" in system and "No way {person} came on stream" in system
    assert "No way" not in user  # per-clip part stays small


def test_no_library_means_no_market_section(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_FORMATS", str(tmp_path / "missing.md"))
    system, _ = W.load_prompt()
    assert "=== TODAY'S MARKET" not in system and "hook .30" in system


def test_market_section_is_capped(tmp_path):
    f = tmp_path / "big.md"
    f.write_text("x" * (W.MARKET_MAX_CHARS * 2), encoding="utf-8")
    assert len(W.market_section(f)) < W.MARKET_MAX_CHARS + 200
