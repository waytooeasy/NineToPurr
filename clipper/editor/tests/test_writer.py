import pytest

import writer as W

GOOD = {"score": 0.8, "in": 100.0, "out": 140.0,
        "hooks": ["He lost the bet", "Chat did this to Kai", "Kai regrets everything"],
        "context_line": "Kai lost a bet to chat and must eat spicy wings",
        "title": "Kai Cenat eats the spiciest wing after losing a bet",
        "music_risk": False}


def mock_llm(monkeypatch, plans):
    seen = []
    monkeypatch.setattr(W, "llm", lambda prompt, schema: seen.append(prompt) or dict(plans[len(seen) - 1]))
    return seen


def test_write_clip_ok_and_prompt_has_inputs(monkeypatch):
    seen = mock_llm(monkeypatch, [GOOD])
    out = W.write_clip("[100.0-110.0] hello chat", "Kai Cenat", {"views_per_hour": 900})
    assert out["in"] == 100.0 and len(out["hooks"]) == 3
    assert "Kai Cenat" in seen[0] and "hello chat" in seen[0] and "900" in seen[0]


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
