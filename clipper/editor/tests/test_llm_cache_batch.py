"""D31: prompt caching, llm_usage logging, Message Batches. SDK mocked, no network."""
import sqlite3
import sys
import types
from pathlib import Path

import pytest

import llm as L

SCHEMA = {"type": "object", "required": ["a"],
          "properties": {"a": {"type": "number", "minimum": 0, "maximum": 1}}}
DB = Path(__file__).resolve().parents[2] / "db"


def make_db(tmp_path):
    p = tmp_path / "clip.db"
    con = sqlite3.connect(p)
    con.executescript((DB / "schema.sql").read_text() + (DB / "ledger.sql").read_text())
    for f in sorted((DB / "migrations").glob("*.sql")):
        con.executescript(f.read_text())
    con.commit()
    con.close()
    return p


def usage(i=10, o=5, cc=0, cr=0):
    return types.SimpleNamespace(input_tokens=i, output_tokens=o,
                                 cache_creation_input_tokens=cc, cache_read_input_tokens=cr)


def msg(text, u):
    return types.SimpleNamespace(content=[types.SimpleNamespace(text=text)], usage=u)


class FakeAnthropic:
    last = None

    def __init__(self):
        FakeAnthropic.last = self
        self.created = []
        self.polls = 0
        self.messages = types.SimpleNamespace(
            create=self._create,
            batches=types.SimpleNamespace(create=self._bcreate, retrieve=self._retrieve,
                                          results=self._results))

    def _create(self, **kw):
        self.created.append(kw)
        return msg('{"a": 0.5}', usage(100, 20, cc=800, cr=0))

    def _bcreate(self, requests):
        self.requests = requests
        return types.SimpleNamespace(id="b1", processing_status="in_progress")

    def _retrieve(self, bid):
        self.polls += 1
        done = "ended" if self.polls >= 2 else "in_progress"
        return types.SimpleNamespace(id=bid, processing_status=done)

    def _results(self, bid):
        def ok(cid, text):
            return types.SimpleNamespace(custom_id=cid, result=types.SimpleNamespace(
                type="succeeded", message=msg(text, usage(50, 10, cr=700))))
        bad = types.SimpleNamespace(custom_id="3", result=types.SimpleNamespace(type="errored"))
        return [ok("1", '{"a": 0.9}'), ok("2", "garbage"), bad]


@pytest.fixture
def fake_sdk(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=FakeAnthropic))
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(L, "_sleep", lambda s: None)


def rows(db):
    con = sqlite3.connect(db)
    r = con.execute("SELECT provider, model, kind, clip_id, batch_id, input_tokens, output_tokens, "
                    "cache_creation_tokens, cache_read_tokens FROM llm_usage").fetchall()
    con.close()
    return r


def test_system_prompt_marked_cacheable(fake_sdk, monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPPER_DB", str(tmp_path / "none.db"))
    assert L.llm("user part", SCHEMA, system="rubric") == {"a": 0.5}
    kw = FakeAnthropic.last.created[0]
    block = kw["system"][0]
    assert block["cache_control"] == {"type": "ephemeral"}
    assert block["text"].startswith("rubric") and "JSON schema" in block["text"]
    assert kw["messages"] == [{"role": "user", "content": "user part"}]


def test_no_system_keeps_old_shape(fake_sdk, monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPPER_DB", str(tmp_path / "none.db"))
    L.llm("p", SCHEMA)
    kw = FakeAnthropic.last.created[0]
    assert "system" not in kw and "JSON schema" in kw["messages"][0]["content"]


def test_usage_logged_per_call(fake_sdk, monkeypatch, tmp_path):
    db = make_db(tmp_path)
    monkeypatch.setenv("CLIPPER_DB", str(db))
    L.llm("p", SCHEMA, system="s")
    assert rows(db) == [("anthropic", "claude-haiku-5-5", "call", None, None, 100, 20, 800, 0)]


def test_usage_log_skipped_without_db_and_never_raises(fake_sdk, monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPPER_DB", str(tmp_path / "missing.db"))
    L.llm("p", SCHEMA)
    assert not (tmp_path / "missing.db").exists()
    bare = tmp_path / "bare.db"
    sqlite3.connect(bare).close()  # exists but has no llm_usage table
    monkeypatch.setenv("CLIPPER_DB", str(bare))
    assert L.llm("p", SCHEMA) == {"a": 0.5}


def test_batch_polls_parses_and_logs(fake_sdk, monkeypatch, tmp_path):
    db = make_db(tmp_path)
    monkeypatch.setenv("CLIPPER_DB", str(db))
    items = [{"id": str(i), "prompt": f"p{i}"} for i in (1, 2, 3)]
    out = L.llm_batch(items, SCHEMA, system="rubric", poll_s=1)
    assert out == {"1": {"a": 0.9}, "2": None, "3": None}
    fa = FakeAnthropic.last
    assert fa.polls == 2 and len(fa.requests) == 3
    p = fa.requests[0]["params"]
    assert fa.requests[0]["custom_id"] == "1" and p["model"] == "claude-haiku-5-5"
    assert p["system"][0]["cache_control"] == {"type": "ephemeral"}
    got = rows(db)
    assert len(got) == 2
    # clip_id is NULL here: no clips row with id 1 exists, but the id is stored as given
    assert got[0][2:] == ("batch", 1, "b1", 50, 10, 0, 700)


def test_batch_guards(fake_sdk, monkeypatch):
    with pytest.raises(L.LLMError):
        L.llm_batch([{"id": "a", "prompt": "x"}, {"id": "a", "prompt": "y"}], SCHEMA)
    assert L.llm_batch([], SCHEMA) == {}
    with pytest.raises(L.LLMError):
        L.llm_batch([{"id": "1", "prompt": "x"}], SCHEMA, poll_s=10, timeout_s=0)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(L.LLMError):
        L.llm_batch([{"id": "1", "prompt": "x"}], SCHEMA)


def test_missing_table_warns(fake_sdk, monkeypatch, tmp_path, caplog):
    bare = tmp_path / "bare.db"
    sqlite3.connect(bare).close()  # migration 006 not run
    monkeypatch.setenv("CLIPPER_DB", str(bare))
    with caplog.at_level("WARNING", logger="llm"):
        assert L.llm("p", SCHEMA) == {"a": 0.5}
    assert "llm_usage not logged" in caplog.text


def test_clip_id_stored_in_llm_usage(fake_sdk, monkeypatch, tmp_path):
    db = make_db(tmp_path)
    monkeypatch.setenv("CLIPPER_DB", str(db))
    L.llm("p", SCHEMA, system="s", clip_id=7)
    assert rows(db)[0][3] == 7


def test_log_usage_connects_with_timeout(fake_sdk, monkeypatch, tmp_path):
    db = make_db(tmp_path)
    monkeypatch.setenv("CLIPPER_DB", str(db))
    seen = {}
    real = sqlite3.connect

    def spy(*a, **kw):
        seen.update(kw)
        return real(*a, **kw)
    monkeypatch.setattr(L.sqlite3, "connect", spy)
    L.llm("p", SCHEMA)
    assert seen.get("timeout") == 30


def test_text_skips_leading_thinking_block():
    # First VM pass (2026-10-19): Haiku 5.5 returned [thinking, text]; content[0].text crashed all 5 clips.
    m = types.SimpleNamespace(stop_reason="end_turn", content=[
        types.SimpleNamespace(type="thinking", thinking="plan the hook..."),
        types.SimpleNamespace(type="text", text='{"a": 0.5}')])
    assert L._text(m) == '{"a": 0.5}'


def test_text_truncated_or_empty_is_an_llm_error():
    with pytest.raises(L.LLMError, match="max_tokens"):
        L._text(types.SimpleNamespace(stop_reason="max_tokens",
                                      content=[types.SimpleNamespace(type="text", text='{"a": 0.')]))
    with pytest.raises(L.LLMError, match="no text"):
        L._text(types.SimpleNamespace(stop_reason="end_turn",
                                      content=[types.SimpleNamespace(type="thinking", thinking="x")]))
