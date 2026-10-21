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


def test_a_remake_is_never_sent_back_for_a_style_rerender(con, add_clip, tmp_path, monkeypatch):
    """D58: a remake is the clipper's edit rebuilt frame for frame; our caption style does not apply."""
    import json
    cid = add_clip()
    con.execute("UPDATE clips SET caption_style='remake', style_version=NULL WHERE id=?", (cid,))
    con.commit()
    sf = tmp_path / "style.json"
    sf.write_text(json.dumps({"caption": {"case": "title", "highlight": "#00FF66"}}))
    monkeypatch.setenv("CLIPPER_STYLE", str(sf))
    ctx = make_ctx(con)
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == 1
    assert st(con, cid) != "needs_rerender"


def test_auto_post_approves_and_sends_stop_button(con, add_clip, monkeypatch):
    monkeypatch.setenv("AUTO_POST", "1")
    cid = add_clip()
    ctx = make_ctx(con)
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == 1
    assert st(con, cid) == "approved"
    kw = ctx.application.bot.send_message.await_args.kwargs
    assert kw["text"].startswith("🚀 Auto-posting")
    assert [b.callback_data for r in kw["reply_markup"].inline_keyboard for b in r] == [f"s:{cid}"]


def test_stop_before_upload_kills_it(con, add_clip, monkeypatch):
    monkeypatch.setenv("AUTO_POST", "1")
    cid = add_clip()
    asyncio.run(approve_bot.push_pending(make_ctx(con).application))
    upd, q = button_update(f"s:{cid}")
    asyncio.run(approve_bot.on_button(upd, make_ctx(con)))
    assert st(con, cid) == "killed"
    con.execute("UPDATE clips SET state='published' WHERE id=?", (cid,))
    upd2, q2 = button_update(f"s:{cid}")              # too late: already uploaded
    asyncio.run(approve_bot.on_button(upd2, make_ctx(con)))
    q2.message.reply_text.assert_awaited_with(f"Clip #{cid} is already uploaded or decided.")


def test_music_risk_still_waits_for_a_tap(con, add_clip, monkeypatch):
    monkeypatch.setenv("AUTO_POST", "1")
    cid = add_clip()
    con.execute("UPDATE clips SET music_risk=1 WHERE id=?", (cid,))
    con.commit()
    ctx = make_ctx(con)
    asyncio.run(approve_bot.push_pending(ctx.application))
    assert st(con, cid) == "qc_passed"
    kw = ctx.application.bot.send_message.await_args.kwargs
    assert [b.callback_data for r in kw["reply_markup"].inline_keyboard for b in r] == [f"p:{cid}", f"k:{cid}"]
    monkeypatch.setenv("AUTO_POST_MUSIC", "1")
    assert approvals.needs_tap(con.execute("SELECT * FROM clips WHERE id=?", (cid,)).fetchone()) is False


def test_auto_post_off_by_default(con, add_clip, monkeypatch):
    monkeypatch.delenv("AUTO_POST", raising=False)
    cid = add_clip()
    asyncio.run(approve_bot.push_pending(make_ctx(con).application))
    assert st(con, cid) == "qc_passed"


def test_bot_token_never_reaches_the_logs(monkeypatch):
    import logging
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "1")
    monkeypatch.setattr(approve_bot, "build_app", lambda *a: NS(run_polling=lambda: None))
    approve_bot.main()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_daily_recap_once_per_day(con, add_clip):
    from datetime import datetime, timezone
    cid = add_clip()
    con.execute("INSERT OR IGNORE INTO accounts (id, platform, handle) VALUES (1, 'youtube', 'peakz')")
    con.execute("INSERT INTO posts (clip_id, account_id, platform_post_id, url, posted_at)"
                " VALUES (?, 1, 'AAA', 'https://youtube.com/shorts/AAA', '2026-10-19 19:20:57')", (cid,))
    con.commit()
    ctx = make_ctx(con)
    early = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)
    assert asyncio.run(approve_bot.push_digest(ctx.application, early)) is False   # before 02:00 UTC
    t = datetime(2026, 10, 20, 2, 5, tzinfo=timezone.utc)
    assert asyncio.run(approve_bot.push_digest(ctx.application, t)) is True
    assert asyncio.run(approve_bot.push_digest(ctx.application, t.replace(hour=9))) is False  # same day
    text = ctx.application.bot.send_message.await_args.kwargs["text"]
    assert text.startswith("Daily recap\n📈 1 Shorts") and "https://youtube.com/shorts/AAA" in text


def test_stats_command(con, add_clip):
    supd, smsg = text_update("/stats")
    asyncio.run(approve_bot.on_stats(supd, make_ctx(con)))
    smsg.reply_text.assert_awaited()
    assert smsg.reply_text.await_args.args[0] == "No Shorts posted yet."


def test_visual_check_gate_holds_unchecked_and_taps_failed(con, add_clip, monkeypatch):
    # Lucas 2026-10-20: "should not repeat mistakes". Unchecked clips wait; failed ones need a tap.
    monkeypatch.setenv("AUTO_POST", "1")
    monkeypatch.setenv("VISUAL_QA", "1")
    ok, bad = add_clip(), add_clip()
    ctx = make_ctx(con)
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == 0          # nothing checked yet
    con.execute("UPDATE clips SET visual_qa=? WHERE id=?", ('{"ok": true, "issues": []}', ok))
    con.execute("UPDATE clips SET visual_qa=? WHERE id=?",
                ('{"ok": false, "issues": [{"code": "double_captions", "frame": 2}]}', bad))
    con.commit()
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == 2
    assert st(con, ok) == "approved" and st(con, bad) == "qc_passed"           # failed one waits for a tap
    texts = [c.kwargs.get("text", "") for c in ctx.application.bot.send_message.await_args_list]
    assert any("visual check: double captions" in t for t in texts)
    unknown = add_clip()
    con.execute("UPDATE clips SET visual_qa=? WHERE id=?", ('{"ok": null, "error": "API down"}', unknown))
    con.commit()
    asyncio.run(approve_bot.push_pending(ctx.application))
    assert st(con, unknown) == "approved"                                       # a broken check never blocks


def test_fyi_names_the_popping_clipper_short_of_the_same_moment(con, add_clip, monkeypatch):
    monkeypatch.setenv("AUTO_POST", "1")
    cid = add_clip()
    con.execute("INSERT INTO radar_candidates (clip_id, creator, title, url, duration_s, view_count, clip_created_at,"
                " views_per_hour, clips_id) VALUES ('c-mom', 'jynxzi', 'mom walked in', 'u', 30, 9, '2026-10-20T04:00:00Z',"
                " 1, ?)", (cid,))
    con.execute("INSERT INTO moment_matches (short_id, streamer, clip_id, short_title, short_vph, candidate_json)"
                " VALUES ('s0', 'Jynxzi', 'c-mom', 'Jynxzi''s Mom Walks In On Stream', 9120, '{}')")
    con.commit()
    ctx = make_ctx(con)
    asyncio.run(approve_bot.push_pending(ctx.application))
    text = ctx.application.bot.send_message.await_args.kwargs["text"]
    assert "🎯 same moment as a popping Short: \"Jynxzi's Mom Walks In On Stream\" (9,120 views/h)" in text
    assert approvals.same_moment_of(con, cid + 1) is None


def test_remake_shows_its_source_short_in_telegram_only(con, add_clip):
    cid = add_clip()
    con.execute("INSERT INTO remakes (short_id, title, vph, status, clip_id) VALUES ('s1', 'Ron Date', 9000, 'done', ?)",
                (cid,))
    con.commit()
    assert approvals.same_moment_of(con, cid) == {"title": "Ron Date", "vph": 9000}
