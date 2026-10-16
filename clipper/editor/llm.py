"""Provider-neutral LLM call: llm(prompt, schema) -> dict.

Default: Anthropic claude-haiku-5-5 (ANTHROPIC_API_KEY from env).
Fallback: Gemini when LLM_PROVIDER=gemini (GEMINI_API_KEY, model GEMINI_MODEL).
The reply must be JSON that satisfies `schema`; one retry on invalid output.
SDKs/HTTP are imported lazily so tests run with no key and no network.
"""
import json
import os
import sqlite3
import time

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-5-5"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_DB = "/opt/clipper/db/clip.db"
_sleep = time.sleep  # tests patch this


class LLMError(RuntimeError):
    pass


def _check(value, schema, path="$"):
    """Minimal JSON-schema subset: type, enum, required, properties, items,
    minItems/maxItems, minimum/maximum, maxLength. Returns list of errors."""
    errs = []
    t = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "boolean": bool,
             "integer": int, "number": (int, float)}
    if t:
        ok = isinstance(value, types[t])
        if t in ("integer", "number") and isinstance(value, bool):
            ok = False
        if not ok:
            return [f"{path}: expected {t}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: not in {schema['enum']}")
    if t == "object":
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}.{k}: missing")
        for k, sub in schema.get("properties", {}).items():
            if k in value:
                errs += _check(value[k], sub, f"{path}.{k}")
    elif t == "array":
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if len(value) > schema.get("maxItems", len(value)):
            errs.append(f"{path}: more than {schema['maxItems']} items")
        for i, v in enumerate(value):
            if "items" in schema:
                errs += _check(v, schema["items"], f"{path}[{i}]")
    elif t in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: above {schema['maximum']}")
    elif t == "string":
        if len(value) > schema.get("maxLength", len(value)):
            errs.append(f"{path}: longer than {schema['maxLength']} chars")
    return errs


def validate(data, schema):
    errs = _check(data, schema)
    if errs:
        raise ValueError("; ".join(errs))
    return data


def _parse_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a < 0 or b <= a:
            raise
        return json.loads(text[a:b + 1])


def _anthropic_model():
    return os.environ.get("CLAUDE_MODEL", DEFAULT_ANTHROPIC_MODEL)


def _system_blocks(system):
    """System prompt as one cacheable block (D31): repeat calls read it from the prompt cache."""
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


def _usage_dict(usage):
    g = lambda k: int(getattr(usage, k, 0) or 0)  # noqa: E731
    return {"input_tokens": g("input_tokens"), "output_tokens": g("output_tokens"),
            "cache_creation_tokens": g("cache_creation_input_tokens"),
            "cache_read_tokens": g("cache_read_input_tokens")}


def log_usage(provider, model, usage, kind="call", clip_id=None, batch_id=None):
    """Insert one llm_usage row (migration 006) when $CLIPPER_DB exists. Never raises:
    cost tracking must not break a clip."""
    path = os.environ.get("CLIPPER_DB", DEFAULT_DB)
    if not os.path.exists(path):
        return
    try:
        con = sqlite3.connect(path)
        try:
            con.execute(
                "INSERT INTO llm_usage (provider, model, kind, clip_id, batch_id, input_tokens, "
                "output_tokens, cache_creation_tokens, cache_read_tokens) VALUES (?,?,?,?,?,?,?,?,?)",
                (provider, model, kind, clip_id, batch_id, usage["input_tokens"],
                 usage["output_tokens"], usage["cache_creation_tokens"],
                 usage["cache_read_tokens"]))
            con.commit()
        finally:
            con.close()
    except sqlite3.Error:
        pass


def _call_anthropic(prompt, system=None, clip_id=None):
    import anthropic  # lazy: not needed in CI
    kw = {"system": _system_blocks(system)} if system else {}
    model = _anthropic_model()
    msg = anthropic.Anthropic().messages.create(
        model=model, max_tokens=1500, messages=[{"role": "user", "content": prompt}], **kw)
    log_usage("anthropic", model, _usage_dict(msg.usage), clip_id=clip_id)
    return msg.content[0].text


def _call_gemini(prompt, system=None, clip_id=None):
    import requests  # lazy
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    if system:
        prompt = system + "\n\n" + prompt
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json"}},
        timeout=60)
    r.raise_for_status()
    body = r.json()
    meta = body.get("usageMetadata", {})
    log_usage("gemini", model, {
        "input_tokens": meta.get("promptTokenCount", 0),
        "output_tokens": meta.get("candidatesTokenCount", 0),
        "cache_creation_tokens": 0,
        "cache_read_tokens": meta.get("cachedContentTokenCount", 0)}, clip_id=clip_id)
    return body["candidates"][0]["content"]["parts"][0]["text"]


def _raw(prompt, system=None, clip_id=None):
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "gemini":
        return _call_gemini(prompt, system, clip_id)
    if provider == "anthropic":
        return _call_anthropic(prompt, system, clip_id)
    raise LLMError(f"unknown LLM_PROVIDER={provider!r}")


def _schema_suffix(schema):
    return ("\n\nReturn ONLY one JSON object matching this JSON schema, "
            "no prose, no code fences:\n" + json.dumps(schema))


def llm(prompt, schema, system=None, clip_id=None):
    """Send `prompt`, return a dict validated against `schema`. One retry.

    `system` is the static part (instructions + rubric); on Anthropic it is marked with
    cache_control so repeat calls hit the prompt cache. Put per-clip input in `prompt`.
    The schema instruction is appended to `system` when given (static, so cached too).
    """
    suffix = _schema_suffix(schema)
    if system:
        system, full = system + suffix, prompt
    else:
        full = prompt + suffix
    last = None
    for _ in range(2):
        text = _raw(full, system, clip_id)
        try:
            return validate(_parse_json(text), schema)
        except ValueError as e:  # includes JSONDecodeError
            last = e
            full = (prompt + ("" if system else suffix) + f"\n\nYour previous reply was invalid ({e}). "
                    "Reply again with valid JSON only.")
    raise LLMError(f"invalid JSON after retry: {last}")


def llm_batch(items, schema, system=None, poll_s=30, timeout_s=24 * 3600):
    """Message Batches API (50% cheaper, results within 24 h) for non-urgent work such as
    re-scoring. Anthropic only. `items`: list of {"id": str, "prompt": str}. Polls until the batch
    ends, then returns {id: validated dict}; an item that errored, expired or failed validation maps
    to None (no retry; resubmit those ids). Token usage is logged per item with kind='batch'.
    """
    if os.environ.get("LLM_PROVIDER", "anthropic").lower() != "anthropic":
        raise LLMError("llm_batch needs LLM_PROVIDER=anthropic")
    if not items:
        return {}
    ids = [it["id"] for it in items]
    if len(set(ids)) != len(ids):
        raise LLMError("duplicate item ids")
    import anthropic  # lazy
    client = anthropic.Anthropic()
    model = _anthropic_model()
    suffix = _schema_suffix(schema)
    sys_text = (system + suffix) if system else None
    requests_ = []
    for it in items:
        params = {"model": model, "max_tokens": 1500,
                  "messages": [{"role": "user", "content": it["prompt"] + ("" if sys_text else suffix)}]}
        if sys_text:
            params["system"] = _system_blocks(sys_text)
        requests_.append({"custom_id": it["id"], "params": params})
    batch = client.messages.batches.create(requests=requests_)
    waited = 0
    while batch.processing_status != "ended":
        if waited >= timeout_s:
            raise LLMError(f"batch {batch.id} not finished after {timeout_s}s")
        _sleep(poll_s)
        waited += poll_s
        batch = client.messages.batches.retrieve(batch.id)
    out = {i: None for i in ids}
    for entry in client.messages.batches.results(batch.id):
        res = entry.result
        if res.type != "succeeded":
            continue
        log_usage("anthropic", model, _usage_dict(res.message.usage), kind="batch",
                  clip_id=int(entry.custom_id) if entry.custom_id.isdigit() else None, batch_id=batch.id)
        try:
            out[entry.custom_id] = validate(_parse_json(res.message.content[0].text), schema)
        except ValueError:
            pass
    return out
