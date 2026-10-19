"""Telegram approval bot (long polling). Gate between qc_passed and approved/killed/needs_rerender.

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_ID, CLIPPER_DB (default /opt/clipper/db/clip.db).
"""
import asyncio
import logging
import os
import sys

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

import approvals

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "editor"))
import style  # noqa: E402  (editor/style.py: today's market caption style)

log = logging.getLogger("approve_bot")
POLL_SECONDS = 30
MAX_UPLOAD_BYTES = 49 * 1024 * 1024  # Bot API upload limit is 50 MB


def keyboard(clip_id: int, n_hooks: int = 0) -> InlineKeyboardMarkup:
    """Lucas (2026-10-19): just Post or Kill. The clip posts as rendered (Writer's best hook)."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Post", callback_data=f"p:{clip_id}"),
        InlineKeyboardButton("❌ Kill", callback_data=f"k:{clip_id}"),
    ]])


def caption(row) -> str:
    text = f"Clip #{row['id']}: {row['title'] or '-'}\n{row['context_line'] or ''}".rstrip()
    if row["music_risk"]:
        text += "\n⚠️ music risk"
    return text[:1000]  # Telegram caption limit is 1024


async def send_clip(bot, chat_id: int, row) -> None:
    kb = keyboard(row["id"], len(approvals.hooks_of(row)))
    path = row["file_path"]
    if path and os.path.isfile(path) and os.path.getsize(path) <= MAX_UPLOAD_BYTES:
        with open(path, "rb") as f:
            await bot.send_video(chat_id=chat_id, video=f, caption=caption(row), reply_markup=kb)
    else:
        note = "\n(video file missing or too big for Telegram)"
        await bot.send_message(chat_id=chat_id, text=caption(row) + note, reply_markup=kb)


async def push_pending(app: Application) -> int:
    """Send every unsent qc_passed clip. Returns how many were sent. A clip rendered in an older
    caption style than today's goes back for a re-render first (Lucas: always recheck the trending
    format before sending)."""
    con, chat_id, sent = app.bot_data["con"], app.bot_data["chat_id"], 0
    current = style.version()
    for row in approvals.pending_to_send(con):
        if row["style_version"] != current:
            approvals.restyle(con, row["id"])
            continue
        try:
            await send_clip(app.bot, chat_id, row)
            approvals.mark_sent(con, row["id"])
            sent += 1
        except Exception as e:  # keep the loop alive; retry next poll
            log.exception("send failed for clip %s", row["id"])
            approvals.record_error(con, row["id"], f"telegram send: {e}")
    return sent


async def _push_loop(app: Application) -> None:
    while True:
        try:
            await push_pending(app)
        except Exception:
            log.exception("push loop error")
        await asyncio.sleep(POLL_SECONDS)


async def _post_init(app: Application) -> None:
    app.bot_data["push_task"] = asyncio.create_task(_push_loop(app))


def _allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.id == context.application.bot_data["chat_id"]


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not _allowed(update, context):
        return  # ignore strangers silently
    await q.answer()
    con = context.application.bot_data["con"]
    try:
        action, clip_id, *rest = q.data.split(":")
        clip_id = int(clip_id)
    except ValueError:
        return

    if action == "p":
        ok = approvals.post(con, clip_id)
        result = f"✅ Posting clip #{clip_id}"
    elif action == "a":  # old messages with hook buttons
        ok = approvals.approve(con, clip_id, int(rest[0]))
        result = f"✅ Approved clip #{clip_id} (hook {rest[0]})"
    elif action == "k":
        ok = approvals.kill(con, clip_id)
        result = f"❌ Killed clip #{clip_id}"
    elif action == "e":
        row = con.execute("SELECT state FROM clips WHERE id = ?", (clip_id,)).fetchone()
        if row is None or row["state"] != approvals.QC_PASSED:
            await q.message.reply_text(f"Clip #{clip_id} already decided.")
            return
        context.application.bot_data["pending_edit"] = clip_id
        await q.message.reply_text(f"Send the new hook for clip #{clip_id} (next message).",
                                   reply_markup=ForceReply(selective=True))
        return
    else:
        return

    await q.message.reply_text(result if ok else f"Clip #{clip_id} already decided.")
    if ok:
        await q.edit_message_reply_markup(reply_markup=None)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update, context):
        return
    data = context.application.bot_data
    clip_id = data.get("pending_edit")
    if clip_id is None:
        return
    ok = approvals.request_rerender(data["con"], clip_id, update.message.text)
    data["pending_edit"] = None
    await update.message.reply_text(
        f"✏️ Re-render requested for clip #{clip_id}." if ok else f"Clip #{clip_id} already decided.")


async def on_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update, context):
        return
    await update.message.reply_text(approvals.status_report(context.application.bot_data["con"]))


def build_app(token: str, chat_id: int, db_path: str) -> Application:
    app = Application.builder().token(token).post_init(_post_init).build()
    app.bot_data.update(con=approvals.connect(db_path), chat_id=chat_id, pending_edit=None)
    app.add_handler(CommandHandler("status", on_status))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_ALLOWED_CHAT_ID")
    if not token or not chat:
        sys.exit("TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_ID are required")
    app = build_app(token, int(chat), os.environ.get("CLIPPER_DB", approvals.DEFAULT_DB))
    app.run_polling()


if __name__ == "__main__":
    main()
