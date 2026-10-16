import pytest

import llm as L

SCHEMA = {"type": "object", "required": ["a"],
          "properties": {"a": {"type": "number", "minimum": 0, "maximum": 1}}}


def fake(monkeypatch, replies):
    calls = []

    def raw(prompt, system=None, clip_id=None):
        calls.append(prompt)
        return replies[len(calls) - 1]
    monkeypatch.setattr(L, "_raw", raw)
    return calls


def test_valid_first_try(monkeypatch):
    calls = fake(monkeypatch, ['{"a": 0.5}'])
    assert L.llm("p", SCHEMA) == {"a": 0.5}
    assert len(calls) == 1


def test_json_inside_prose_and_fences(monkeypatch):
    fake(monkeypatch, ['```json\n{"a": 1}\n```'])
    assert L.llm("p", SCHEMA) == {"a": 1}


def test_one_retry_on_invalid_json(monkeypatch):
    calls = fake(monkeypatch, ["nope", '{"a": 0.2}'])
    assert L.llm("p", SCHEMA) == {"a": 0.2}
    assert len(calls) == 2 and "invalid" in calls[1]


def test_retry_on_schema_violation_then_fail(monkeypatch):
    calls = fake(monkeypatch, ['{"a": 5}', '{"a": 9}'])
    with pytest.raises(L.LLMError):
        L.llm("p", SCHEMA)
    assert len(calls) == 2


def test_default_provider_is_haiku(monkeypatch):
    assert L.DEFAULT_ANTHROPIC_MODEL == "claude-haiku-5-5"
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    seen = []
    monkeypatch.setattr(L, "_call_anthropic", lambda p, *a: seen.append("a") or '{"a": 0}')
    monkeypatch.setattr(L, "_call_gemini", lambda p, *a: seen.append("g") or '{"a": 0}')
    L.llm("p", SCHEMA)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    L.llm("p", SCHEMA)
    assert seen == ["a", "g"]


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "x")
    with pytest.raises(L.LLMError):
        L.llm("p", SCHEMA)
