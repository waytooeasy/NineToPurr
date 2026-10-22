"""DB logic for the approval gate. Pure sqlite3, no Telegram, easy to test."""
import json
import os
import sqlite3

DEFAULT_DB = "/opt/clipper/db/clip.db"  # shared default for upload.py and approve_bot.py
QC_PASSED = "qc_passed"


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def hooks_of(row) -> list[str]:
    try:
        hooks = json.loads(row["hooks_json"] or "[]")
    except (TypeError, ValueError):
        return []
    return [str(h) for h in hooks][:3]


def pending_to_send(con):
    """Clips at qc_passed that Lucas has not been sent yet."""
    return con.execute(
        "SELECT * FROM clips WHERE state = ? AND approval_sent_at IS NULL ORDER BY id",
        (QC_PASSED,),
    ).fetchall()


def remake_match(row):
    """The remake's match score vs the clipper's original (remake/match.py, in the render sidecar json), or None."""
    try:
        f = os.path.splitext(row["file_path"] or "")[0] + ".json"
        with open(f) as fh:
            m = json.load(fh).get("match")
    except (OSError, ValueError, IndexError, KeyError, TypeError, AttributeError):
        return None
    return m if isinstance(m, dict) and "picture" in m else None


def is_remake(row) -> bool:
    """A remake (D58) is the clipper's edit rebuilt frame for frame: never re-cut in our caption style."""
    try:
        return (row["caption_style"] or "") == "remake"
    except (IndexError, KeyError):
        return False


def creator_of(con, clip_id: int):
    """Radar creator login/slug of a clip (radar_candidates.creator), or None."""
    try:
        r = con.execute("SELECT creator FROM radar_candidates WHERE clips_id = ?", (clip_id,)).fetchone()
    except sqlite3.Error:
        return None
    return r[0] if r else None


def same_moment_of(con, clip_id: int):
    """The popping clipper Short this clip is the same moment as (radar/match.py, D54): {title, vph} or None."""
    try:
        # a remake (D58): the clipper Short it rebuilds. Shown in Telegram only, never in the YouTube description
        r = con.execute("SELECT title, vph FROM remakes WHERE clip_id = ?", (clip_id,)).fetchone()
        if r:
            return {"title": r[0], "vph": r[1]}
        r = con.execute("SELECT m.short_title, m.short_vph FROM moment_matches m JOIN radar_candidates r"
                        " ON r.clip_id = m.clip_id WHERE r.clips_id = ? ORDER BY m.short_vph DESC LIMIT 1",
                        (clip_id,)).fetchone()
    except sqlite3.Error:
        return None
    return {"title": r[0], "vph": r[1]} if r else None


def mark_sent(con, clip_id: int) -> None:
    con.execute("UPDATE clips SET approval_sent_at = datetime('now') WHERE id = ?", (clip_id,))
    con.commit()


def record_error(con, clip_id: int, msg: str) -> None:
    con.execute("UPDATE clips SET last_error = ?, state_changed_at = datetime('now') WHERE id = ?",
                (msg[:500], clip_id))
    con.commit()


def _decide(con, clip_id, new_state, hook_index, hook_text, set_hook) -> bool:
    """Move qc_passed -> new_state atomically. False if the clip was not waiting (double tap)."""
    with con:
        cur = con.execute(
            "UPDATE clips SET state = ?, state_changed_at = datetime('now'),"
            " hook_text = CASE WHEN ? THEN ? ELSE hook_text END"
            " WHERE id = ? AND state = ?",
            (new_state, int(set_hook), hook_text, clip_id, QC_PASSED),
        )
        if cur.rowcount != 1:
            return False
        con.execute(
            "INSERT INTO approvals (clip_id, decision, hook_index, chosen_hook) VALUES (?,?,?,?)",
            (clip_id, new_state, hook_index, hook_text),
        )
    return True


def approve(con, clip_id: int, hook_index: int) -> bool:
    row = con.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if row is None:
        return False
    hooks = hooks_of(row)
    if not 1 <= hook_index <= len(hooks):
        return False
    return _decide(con, clip_id, "approved", hook_index, hooks[hook_index - 1], True)


def post(con, clip_id: int) -> bool:
    """✅ Post: approve the clip exactly as rendered (its current hook_text)."""
    row = con.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if row is None:
        return False
    hooks = hooks_of(row)
    idx = hooks.index(row["hook_text"]) + 1 if row["hook_text"] in hooks else None
    return _decide(con, clip_id, "approved", idx, row["hook_text"], False)


def restyle(con, clip_id: int) -> bool:
    """qc_passed -> needs_rerender without changing the hook: the market style changed after this
    clip was rendered, so it is re-cut in today's style before Lucas sees it."""
    with con:
        cur = con.execute(
            "UPDATE clips SET state = 'needs_rerender', state_changed_at = datetime('now')"
            " WHERE id = ? AND state = ? AND approval_sent_at IS NULL", (clip_id, QC_PASSED))
    return cur.rowcount == 1


def auto_post_enabled(env=None) -> bool:
    """AUTO_POST=1 in /opt/clipper/.env: clips post without a tap (Lucas, 2026-10-19)."""
    e = os.environ if env is None else env
    return str(e.get("AUTO_POST", "")).strip().lower() in ("1", "true", "yes", "on")


def visual_qa_enabled(env=None) -> bool:
    """VISUAL_QA=0 turns the pre-post visual check (editor/visual_qa.py) off."""
    e = os.environ if env is None else env
    return str(e.get("VISUAL_QA", "1")).strip().lower() not in ("0", "false", "no", "off")


def vqa_issues(row) -> list:
    """Issue codes when the visual check failed this clip (clips.visual_qa, migration 010), else []."""
    try:
        d = json.loads(row["visual_qa"] or "{}")
    except (IndexError, KeyError, ValueError, TypeError):
        return []
    return [str(i.get("code")) for i in d.get("issues") or [] if isinstance(i, dict)] if d.get("ok") is False else []


def vqa_pending(row, env=None) -> bool:
    """The pipeline has not looked at this clip yet: hold it (never send it unchecked)."""
    try:
        return visual_qa_enabled(env) and row["visual_qa"] is None
    except (IndexError, KeyError):
        return False


def needs_tap(row, env=None) -> bool:
    """Even with AUTO_POST, a clip waits for Lucas when it has music risk (AUTO_POST_MUSIC=1 posts those
    too: a music claim can block or demonetise a Short) or failed the visual check."""
    e = os.environ if env is None else env
    music_ok = str(e.get("AUTO_POST_MUSIC", "")).strip().lower() in ("1", "true", "yes", "on")
    remake_ok = str(e.get("AUTO_POST_REMAKES", "")).strip().lower() in ("1", "true", "yes", "on")
    if is_remake(row) and not remake_ok:   # Lucas checks each remake next to the original first (2026-10-21)
        return True
    return (bool(row["music_risk"]) and not music_ok) or bool(vqa_issues(row))


def stop(con, clip_id: int) -> bool:
    """🛑 Stop an auto-posted clip before the uploader takes it: approved -> killed."""
    with con:
        cur = con.execute(
            "UPDATE clips SET state = 'killed', state_changed_at = datetime('now')"
            " WHERE id = ? AND state = 'approved'", (clip_id,))
        if cur.rowcount != 1:
            return False
        con.execute("INSERT INTO approvals (clip_id, decision, hook_index, chosen_hook) VALUES (?,?,?,?)",
                    (clip_id, "killed", None, None))
    return True


def kill(con, clip_id: int) -> bool:
    return _decide(con, clip_id, "killed", None, None, False)


def request_rerender(con, clip_id: int, new_hook: str) -> bool:
    new_hook = new_hook.strip()
    if not new_hook:
        return False
    return _decide(con, clip_id, "needs_rerender", None, new_hook, True)


def status_report(con) -> str:
    counts = con.execute(
        "SELECT state, COUNT(*) n FROM clips"
        " WHERE date(COALESCE(state_changed_at, created_at)) = date('now')"
        " GROUP BY state ORDER BY state"
    ).fetchall()
    oldest = con.execute(
        "SELECT CAST((julianday('now') - julianday(COALESCE(state_changed_at, created_at))) * 24 * 60 AS INTEGER)"
        " FROM clips WHERE state = ? ORDER BY COALESCE(state_changed_at, created_at) LIMIT 1",
        (QC_PASSED,),
    ).fetchone()
    waiting = con.execute("SELECT COUNT(*) FROM clips WHERE state = ?", (QC_PASSED,)).fetchone()[0]
    err = con.execute(
        "SELECT id, last_error FROM clips WHERE last_error IS NOT NULL"
        " ORDER BY state_changed_at DESC, id DESC LIMIT 1"
    ).fetchone()

    lines = ["Today:"]
    lines += [f"  {r['state']}: {r['n']}" for r in counts] or ["  no clips yet"]
    lines.append(f"Waiting for you: {waiting}" + (f" (oldest {oldest[0]} min)" if oldest else ""))
    lines.append(f"Last error: clip {err['id']}: {err['last_error']}" if err else "Last error: none")
    return "\n".join(lines)
