"""Visual check of every finished Short before it can post (Lucas 2026-10-20: "should not repeat mistakes").

Unit tests check code, not the picture. Day 1 shipped emoji boxes in the hook, a 100 px corner cam blown
up to the top panel and a second caption track on Sykkuno's live captions. This looks at 3 frames of the
rendered file (hook at 1 s, ~45 %, ~80 %) with Claude Haiku (vision) against a fixed checklist.

- pass  -> the clip goes on as before (auto-post)
- fail  -> it waits in Telegram for ✅ Post / ❌ Kill with the issues listed (approvals.needs_tap)
- error (no key, API down) -> {"ok": null}: the clip goes on; the check never blocks the channel
Stored as JSON in clips.visual_qa (migration 010); a re-render clears it so the new file is checked.

    python clipper/editor/visual_qa.py FILE.mp4 [...]   # check files by hand, prints the JSON
"""
import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

MODEL = "claude-haiku-5-5"
CODES = {
    "double_captions": "two caption tracks at once (e.g. the streamer's own captions plus ours)",
    "broken_glyphs": "boxes, squares or garbled symbols where a character should be",
    "blurry_panel": "a panel or the whole frame is a heavily blown-up, blurry low-resolution crop",
    "bad_crop": "the main subject (face / action) is cut off or the frame shows mostly nothing",
    "text_overlap": "two text blocks overlap or text runs off the screen edge",
    "black_bars": "black or blurred bars / letterboxing",
    "no_watermark": "no small '@Peakz.Recaps' handle near the bottom centre",
}
PROMPT = (
    "These are 3 frames (1080x1920) from one finished YouTube Short made by a stream-clip channel. "
    "Expected look: full-bleed 9:16 video (or a facecam panel on top of gameplay), ONE caption line of "
    "2-3 heavy words mid-screen, a short hook line near the top in the first frame only, and a small "
    "semi-transparent '@Peakz.Recaps' handle near the bottom centre. Game UI / HUD text and text that is "
    "part of the scene (signs, shirts, overlays of the stream) are fine.\n"
    "Report only clear problems from this list:\n"
    + "\n".join(f"- {k}: {v}" for k, v in CODES.items())
    + "\nAnswer with JSON only: {\"ok\": true} or {\"ok\": false, \"issues\": [{\"code\": \"<code>\", "
    "\"frame\": <1-3>, \"note\": \"<6 words max>\"}]}"
)


def duration(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(video)], capture_output=True, text=True, check=True).stdout
    return float(out.strip() or 0)


def frames(video, run=subprocess.run):
    """JPEG bytes of 3 frames: the hook at 1 s, then ~45 % and ~80 % in."""
    d = duration(video)
    out = []
    for t in (min(1.0, d / 4), d * 0.45, d * 0.8):
        r = run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                 "-vf", "scale=540:960", "-f", "image2", "-c:v", "mjpeg", "-q:v", "4", "-"],
                capture_output=True, check=True)
        out.append(r.stdout)
    return out


def anthropic_vision(images, prompt=PROMPT):
    import anthropic  # lazy
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.b64encode(b).decode()}} for b in images]
    content.append({"type": "text", "text": prompt})
    # thinking off: Haiku 5.5 otherwise spends the budget thinking and returns no text (style scout, VM)
    msg = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=600, thinking={"type": "disabled"},
                                                messages=[{"role": "user", "content": content}])
    try:
        import llm  # editor/llm.py: cost tracking in llm_usage, never raises
        llm.log_usage("anthropic", MODEL, llm._usage_dict(msg.usage))
    except Exception:  # noqa: BLE001
        pass
    return "".join(b.text for b in msg.content if b.type == "text")


def parse(text):
    """Model reply -> {"ok": bool, "issues": [...]} with only known codes; None if unreadable."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    issues = [i for i in d.get("issues") or [] if isinstance(i, dict) and i.get("code") in CODES]
    if d.get("ok") is True and not issues:
        return {"ok": True, "issues": []}
    if issues:
        return {"ok": False, "issues": issues}
    return {"ok": True, "issues": []} if d.get("ok") is not False else None


def check(video, vision=None, grab=frames):
    """{"ok": True|False|None, "issues": [...], "at": ...}. Any error -> ok None (never blocks)."""
    at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        if vision is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                return {"ok": None, "issues": [], "error": "no ANTHROPIC_API_KEY", "at": at}
            vision = anthropic_vision
        res = parse(vision(grab(video)))
        if res is None:
            return {"ok": None, "issues": [], "error": "unreadable reply", "at": at}
        return {**res, "at": at}
    except Exception as e:  # noqa: BLE001 - the check must never stop the channel
        return {"ok": None, "issues": [], "error": f"{type(e).__name__}: {e}"[:200], "at": at}


def enabled(env=None):
    """VISUAL_QA=0 in /opt/clipper/.env turns the check off."""
    e = os.environ if env is None else env
    return str(e.get("VISUAL_QA", "1")).strip().lower() not in ("0", "false", "no", "off")


def run(con, vision=None, grab=frames):
    """Check every qc_passed clip that has no result yet. -> {"passed": [ids], "failed": {id: codes}}."""
    res = {"passed": [], "failed": {}, "unchecked": []}
    if not enabled():
        return res
    rows = con.execute("SELECT id, file_path FROM clips WHERE state='qc_passed' AND visual_qa IS NULL"
                       " ORDER BY id").fetchall()
    for cid, path in rows:
        r = check(path, vision, grab) if path and os.path.isfile(path) else \
            {"ok": None, "issues": [], "error": "file missing"}
        con.execute("UPDATE clips SET visual_qa=? WHERE id=? AND visual_qa IS NULL", (json.dumps(r), cid))
        con.commit()
        if r["ok"] is False:
            res["failed"][cid] = [i["code"] for i in r["issues"]]
        elif r["ok"]:
            res["passed"].append(cid)
        else:
            res["unchecked"].append(cid)
    return res


def failed(row):
    """Issue codes if this clips row failed the visual check, else []."""
    try:
        raw = row["visual_qa"]
    except (IndexError, KeyError):
        return []
    try:
        d = json.loads(raw) if raw else {}
    except ValueError:
        return []
    return [i.get("code") for i in d.get("issues") or []] if d.get("ok") is False else []


def main(argv=None):
    for f in (argv if argv is not None else sys.argv[1:]):
        print(f, json.dumps(check(f), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
