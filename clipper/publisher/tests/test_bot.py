import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import approve_bot
import approvals

ALLOWED = 111


def make_ctx(con):
    app = NS(bot_data={"con": con, "chat_id": ALLOWED, "pending_edit": None}, bot=AsyncMock())
    return NS(application=app)


def button_update(data, chat_id=ALLOWED):
    q = NS(data=data, answer=AsyncMock(), edit_message_reply_markup=AsyncMock(),
           message=NS(reply_text=AsyncMock()))
    return NS(callback_query=q, effective_chat=NS(id=chat_id)), q


def text_update(text, chat_id=ALLOWED):
    msg = NS(text=text, reply_text=AsyncMock())
    return NS(message=msg, effective_chat=NS(id=chat_id)), msg


def st(con, cid):
    return con.execute("SELECT state FROM clips WHERE id=?", (cid,)).fetchone()[0]


def test_push_sends_text_when_no_file_and_marks_sent(con, add_clip):
    add_clip()
    ctx = make_ctx(con)
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == 1
    kw = ctx.application.bot.send_message.await_args.kwargs
    assert kw["chat_id"] == ALLOWED and "Kai loses it" in kw["text"]
    assert [b.callback_data for r in kw["reply_markup"].inline_keyboard for b in r] == ["p:1", "k:1"]
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == 0  # not sent twice


def test_push_sends_video_when_file_exists(con, add_clip, tmp_path):
    f = tmp_path / "c.mp4"
    f.write_bytes(b"x")
    add_clip(path=str(f))
    ctx = make_ctx(con)
    asyncio.run(approve_bot.push_pending(ctx.application))
    ctx.application.bot.send_video.assert_awaited_once()


def test_push_failure_records_error_and_retries(con, add_clip):
    cid = add_clip()
    ctx = make_ctx(con)
    ctx.application.bot.send_message.side_effect = RuntimeError("down")
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == 0
    assert "down" in con.execute("SELECT last_error FROM clips WHERE id=?", (cid,)).fetchone()[0]
    assert len(approvals.pending_to_send(con)) == 1


def test_approve_button(con, add_clip):
    cid = add_clip()
    upd, _ = button_update(f"a:{cid}:3")
    asyncio.run(approve_bot.on_button(upd, make_ctx(con)))
    assert st(con, cid) == "approved"
    assert con.execute("SELECT hook_text FROM clips WHERE id=?", (cid,)).fetchone()[0] == "h three"


def test_kill_button(con, add_clip):
    cid = add_clip()
    upd, _ = button_update(f"k:{cid}")
    asyncio.run(approve_bot.on_button(upd, make_ctx(con)))
    assert st(con, cid) == "killed"


def test_edit_flow(con, add_clip):
    cid = add_clip()
    ctx = make_ctx(con)
    upd, _ = button_update(f"e:{cid}")
    asyncio.run(approve_bot.on_button(upd, ctx))
    assert st(con, cid) == "qc_passed"  # nothing decided until the text arrives
    tupd, _ = text_update("new hook!")
    asyncio.run(approve_bot.on_text(tupd, ctx))
    assert st(con, cid) == "needs_rerender"
    assert con.execute("SELECT hook_text FROM clips WHERE id=?", (cid,)).fetchone()[0] == "new hook!"


def test_stranger_is_ignored(con, add_clip):
    cid = add_clip()
    ctx = make_ctx(con)
    upd, q = button_update(f"a:{cid}:1", chat_id=999)
    asyncio.run(approve_bot.on_button(upd, ctx))
    q.answer.assert_not_awaited()
    ctx.application.bot_data["pending_edit"] = cid
    tupd, _ = text_update("evil", chat_id=999)
    asyncio.run(approve_bot.on_text(tupd, ctx))
    supd, smsg = text_update("/status", chat_id=999)
    asyncio.run(approve_bot.on_status(supd, ctx))
    smsg.reply_text.assert_not_awaited()
    assert st(con, cid) == "qc_passed"


def test_status_command(con, add_clip):
    add_clip()
    upd, msg = text_update("/status")
    asyncio.run(approve_bot.on_status(upd, make_ctx(con)))
    assert "Waiting for you: 1" in msg.reply_text.await_args.args[0]


def test_stale_button_after_decision(con, add_clip):
    cid = add_clip()
    ctx = make_ctx(con)
    asyncio.run(approve_bot.on_button(button_update(f"k:{cid}")[0], ctx))
    upd, q = button_update(f"a:{cid}:1")
    asyncio.run(approve_bot.on_button(upd, ctx))
    assert st(con, cid) == "killed"
    assert "already decided" in q.message.reply_text.await_args.args[0]


def test_keyboard_is_post_or_kill():
    kb = approve_bot.keyboard(7)
    btns = [b for row in kb.inline_keyboard for b in row]
    assert [(b.text, b.callback_data) for b in btns] == [("✅ Post", "p:7"), ("❌ Kill", "k:7")]


def test_post_button_approves_as_rendered(con, add_clip):
    cid = add_clip()
    rendered = con.execute("SELECT hook_text FROM clips WHERE id=?", (cid,)).fetchone()[0]
    upd, _ = button_update(f"p:{cid}")
    asyncio.run(approve_bot.on_button(upd, make_ctx(con)))
    assert st(con, cid) == "approved"
    assert con.execute("SELECT hook_text FROM clips WHERE id=?", (cid,)).fetchone()[0] == rendered
    upd2, q2 = button_update(f"p:{cid}")   # double tap
    asyncio.run(approve_bot.on_button(upd2, make_ctx(con)))
    q2.message.reply_text.assert_awaited_with(f"Clip #{cid} already decided.")


def test_clip_in_an_old_style_goes_back_for_rerender_not_to_lucas(con, add_clip, tmp_path, monkeypatch):
    import json
    import style
    cid = add_clip()                                   # rendered in the default style
    sf = tmp_path / "style.json"
    sf.write_text(json.dumps({"caption": {"case": "title", "highlight": "#00FF66"}}))
    monkeypatch.setenv("CLIPPER_STYLE", str(sf))       # market moved on
    ctx = make_ctx(con)
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == 0
    ctx.application.bot.send_message.assert_not_awaited()
    assert st(con, cid) == "needs_rerender"
    con.execute("UPDATE clips SET state='qc_passed', style_version=? WHERE id=?", (style.version(), cid))
    con.commit()                                        # re-rendered in today's style
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == 1
