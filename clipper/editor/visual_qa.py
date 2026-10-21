"""Visual check of every finished Short before it can post (Lucas 2026-10-20: "should not repeat mistakes").

Unit tests check code, not the picture. Day 1 shipped emoji boxes in the hook, a 100 px corner cam blown
up to the top panel and a second caption track on Sykkuno's live captions. This looks at 3 frames of the
rendered file (hook at 1 s, ~45 %, ~80 %) with Claude Haiku (vision) against a fixed checklist.

- a failure counts only when a second look flags the same problem (VM test: one of two looks called our own
  white header box "double captions"; Sykkuno's real double captions were flagged every time)
- pass  -> the clip goes on as before (auto-post)
- double captions on a streamer not known to caption their stream -> learned (creator_flags), the clip is
  re-rendered without our captions and checked again (Sykkuno, Valkyrae). For a streamer we draw no captions
  for, captions on screen are theirs: never "double" (Stable Ronaldo's re-render waited for a tap, 2026-10-21)
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
    "These are 3 frames (1080x1920) from one finished YouTube Short made by a stream-clip channel.\n"
    "OUR text on it is exactly: (a) ONE caption line of 1-5 heavy words with an outline (wide or condensed "
    "font, any case) in the middle or lower part of the screen, (b) a short hook/title line higher up or on the "
    "seam: either only in frame 1, or staying in every frame (possibly as dark text in a white box), (c) a "
    "small semi-transparent '@Peakz.Recaps' handle near the bottom centre.\n"
    "Check each frame carefully for these problems:\n"
    "- double_captions: ANY other subtitle-style text that transcribes speech is visible at the same time as "
    "our caption, e.g. the streamer's own live captions (usually sentence-case or lowercase white text near "
    "the bottom, sometimes with one coloured word). Report it even if both look clean. Game menus/HUD, chat, "
    "signs and stream overlays are not captions.\n"
    "- broken_glyphs: boxes, squares, empty rectangles or garbled symbols inside any of OUR text.\n"
    "- blurry_panel: a panel or the whole frame is a heavily blown-up, blurry low-resolution crop.\n"
    "- bad_crop: the main subject (face / action) is cut off or the frame shows mostly nothing.\n"
    "- text_overlap: two of OUR text blocks overlap each other, or text runs off the screen edge.\n"
    "- black_bars: black or blurred bars / letterboxing.\n"
    "- no_watermark: the '@Peakz.Recaps' handle is missing.\n"
    "Answer with JSON only: {\"ok\": true} or {\"ok\": false, \"issues\": [{\"code\": \"<code>\", "
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


def prompt_for(expected=None):
    """The checklist plus exactly what this clip burns in (hook/header text and mode), so our own header box
    is never mistaken for a second caption track (Lacy preview, 2026-10-20)."""
    if not expected:
        return PROMPT
    hook, header = (expected.get("hook") or "").strip(), expected.get("header") or "none"
    where = {"white_box": "as dark text in a WHITE BOX that stays in every frame",
             "text": "as a title line that stays in every frame",
             "none": "in frame 1 only"}.get(header, "in frame 1 only")
    own = f"OUR hook/title text on this clip is \"{hook}\", shown {where}. " if hook else ""
    if expected.get("fit"):
        own += ("This clip intentionally shows a wide video panel across the middle with a blurred copy of the same "
                "video above and below (like the top clip channels): that is not black_bars. ")
    if expected.get("chat_panel"):
        own += ("The lower part of this clip is a panel showing the stream's own chat (usernames and messages): "
                "that is intended, not captions; our handle sits just above it. ")
    if expected.get("own_captions"):
        own += ("This clip has NO caption line of ours: the speech captions you see are the streamer's own live "
                "captions, which is fine; report double_captions only if two different caption tracks show at once. ")
    return PROMPT.replace("Check each frame carefully", own + "Everything else that transcribes speech "
                          "is NOT ours. Check each frame carefully", 1)


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


def check(video, vision=None, grab=frames, expected=None):
    """{"ok": True|False|None, "issues": [...], "at": ...}. Any error -> ok None (never blocks).
    `expected`: {"hook", "header"} burned into this clip (see prompt_for)."""
    at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        if vision is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                return {"ok": None, "issues": [], "error": "no ANTHROPIC_API_KEY", "at": at}
            p = prompt_for(expected)
            vision = lambda imgs: anthropic_vision(imgs, p)  # noqa: E731
        imgs = grab(video)
        reply = vision(imgs)
        res = parse(reply)
        if res is None:
            return {"ok": None, "issues": [], "error": "unreadable reply", "raw": str(reply)[:300], "at": at}
        if res["ok"] is False:
            # a second, independent look must flag the same problem: one odd reply must not hold a good clip
            again = parse(vision(imgs)) or {"ok": None, "issues": []}
            codes = {i.get("code") for i in again.get("issues") or []}
            kept = [i for i in res["issues"] if i.get("code") in codes]
            if not kept:
                return {"ok": True, "issues": [], "unconfirmed": [i.get("code") for i in res["issues"]], "at": at}
            res = {"ok": False, "issues": kept}
        return {**res, "at": at}
    except Exception as e:  # noqa: BLE001 - the check must never stop the channel
        return {"ok": None, "issues": [], "error": f"{type(e).__name__}: {e}"[:200], "at": at}


def enabled(env=None):
    """VISUAL_QA=0 in /opt/clipper/.env turns the check off."""
    e = os.environ if env is None else env
    return str(e.get("VISUAL_QA", "1")).strip().lower() not in ("0", "false", "no", "off")


def _header_for(creator):
    try:
        import style
        return style.load(creator=creator).get("header", "none")
    except Exception:  # noqa: BLE001
        return "none"


def learn_own_captions(con, creator, clip_id):
    """Remember that this streamer's stream shows live captions (creator_flags). -> True if new."""
    if not creator:
        return False
    cur = con.execute("INSERT INTO creator_flags (creator, own_captions, note) VALUES (?, 1, ?)"
                      " ON CONFLICT(creator) DO NOTHING",
                      (creator.lower(), f"visual check: double captions on clip {clip_id}"))
    return cur.rowcount == 1


def render_info(path):
    try:
        return json.loads(open(os.path.splitext(str(path))[0] + ".json", encoding="utf-8").read())
    except (OSError, ValueError, TypeError):
        return {}


def drew_captions(path, con, creator):
    """Did the Editor burn our caption track into this file? The render info next to it says (clip.py
    write_render_info); older renders: not for a streamer with their own captions."""
    try:
        return bool(json.loads(open(os.path.splitext(str(path))[0] + ".json", encoding="utf-8").read())["our_captions"])
    except (OSError, ValueError, KeyError, TypeError):
        return not has_own_captions(con, creator)


def has_own_captions(con, creator):
    """True when the Editor draws no captions for this creator (their stream shows live captions)."""
    if not creator:
        return False
    try:
        if con.execute("SELECT 1 FROM creator_flags WHERE creator=? AND own_captions=1", (creator.lower(),)).fetchone():
            return True
    except Exception:  # noqa: BLE001 - table missing on an old DB
        pass
    try:
        import clip
        return creator.lower() in clip.own_caption_logins()
    except Exception:  # noqa: BLE001
        return False


def run(con, vision=None, grab=frames):
    """Check every qc_passed clip that has no result yet. -> {"passed": [ids], "failed": {id: codes},
    "rerender": [ids]}. Double captions on a streamer we did not know shows live captions: learn it and
    re-render the clip without ours (one automatic retry; after that it waits for a tap like any failure)."""
    res = {"passed": [], "failed": {}, "unchecked": [], "rerender": []}
    if not enabled():
        return res
    rows = con.execute("SELECT c.id, c.file_path, r.creator, c.hook_text FROM clips c"
                       " LEFT JOIN radar_candidates r ON r.clips_id = c.id"
                       " WHERE c.state='qc_passed' AND c.visual_qa IS NULL ORDER BY c.id").fetchall()
    for cid, path, creator, hook in rows:
        theirs = not drew_captions(path, con, creator)     # no track of ours: captions on screen are theirs
        mode = render_info(path).get("mode")
        expected = {"hook": hook, "header": _header_for(creator), "own_captions": theirs,
                    "chat_panel": mode == "chatstack", "fit": mode == "fit"}
        r = check(path, vision, grab, expected) if path and os.path.isfile(path) else \
            {"ok": None, "issues": [], "error": "file missing"}
        drop = ({"double_captions"} if theirs else set()) | ({"black_bars"} if mode == "fit" else set())
        if drop and r["ok"] is False:    # no caption track of ours / a blurred fill we chose: not a failure
            left = [i for i in r["issues"] if i.get("code") not in drop]
            ignored = sorted({i.get("code") for i in r["issues"]} - {i.get("code") for i in left})
            r = {**r, "issues": left, "ok": not left or False}
            if not left:
                r["ignored"] = ignored
        codes = {i.get("code") for i in r.get("issues") or []}
        if r["ok"] is False and "double_captions" in codes and learn_own_captions(con, creator, cid) \
                and codes == {"double_captions"}:
            con.execute("UPDATE clips SET state='needs_rerender', state_changed_at=datetime('now'),"
                        " visual_qa=NULL WHERE id=?", (cid,))
            con.commit()
            res["rerender"].append(cid)
            continue
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
