"""Provider-neutral LLM call: llm(prompt, schema) -> dict.

Default: Anthropic claude-haiku-5-5 (ANTHROPIC_API_KEY from env).
Fallback: Gemini when LLM_PROVIDER=gemini (GEMINI_API_KEY, model GEMINI_MODEL).
The reply must be JSON that satisfies `schema`; one retry on invalid output.
SDKs/HTTP are imported lazily so tests run with no key and no network.
"""
import json
import os

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-5-5"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"


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


def _call_anthropic(prompt):
    import anthropic  # lazy: not needed in CI
    msg = anthropic.Anthropic().messages.create(
        model=os.environ.get("CLAUDE_MODEL", DEFAULT_ANTHROPIC_MODEL),
        max_tokens=1500, messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text


def _call_gemini(prompt):
    import requests  # lazy
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json"}},
        timeout=60)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _raw(prompt):
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "gemini":
        return _call_gemini(prompt)
    if provider == "anthropic":
        return _call_anthropic(prompt)
    raise LLMError(f"unknown LLM_PROVIDER={provider!r}")


def llm(prompt, schema):
    """Send `prompt`, return a dict validated against `schema`. One retry."""
    suffix = ("\n\nReturn ONLY one JSON object matching this JSON schema, "
              "no prose, no code fences:\n" + json.dumps(schema))
    full = prompt + suffix
    last = None
    for _ in range(2):
        text = _raw(full)
        try:
            return validate(_parse_json(text), schema)
        except ValueError as e:  # includes JSONDecodeError
            last = e
            full = (prompt + suffix + f"\n\nYour previous reply was invalid ({e}). "
                    "Reply again with valid JSON only.")
    raise LLMError(f"invalid JSON after retry: {last}")
