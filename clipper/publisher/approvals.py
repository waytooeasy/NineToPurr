"""DB logic for the approval gate. Pure sqlite3, no Telegram, easy to test."""
import json
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
