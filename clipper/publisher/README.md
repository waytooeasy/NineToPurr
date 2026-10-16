# Publisher

**Scope:** (1) the Telegram approval gate (`approve_bot.py`, built); (2) upload approved Shorts to YouTube on a spaced schedule (not built).

**Status:** approval bot built. Upload not built.

## Approval bot (D10: Lucas approves every Short)

When a clip reaches `qc_passed`, the bot sends the mp4 (or text only if the file is missing or over 49 MB), the context line and the 3 hooks.

| Button | Result |
|---|---|
| ✅ Hook 1/2/3 | `approved`, chosen hook saved to `clips.hook_text` |
| ✏️ Edit hook | bot asks for text; your next message becomes the hook, state `needs_rerender` |
| ❌ Kill | `killed` |

- `/status`: today's counts per state, how many wait for you and the oldest age, last error.
- Only `TELEGRAM_ALLOWED_CHAT_ID` gets answers; everyone else is ignored silently.
- Decisions only apply to clips still in `qc_passed`, so a stale or double tap does nothing.
- Every decision is also logged in the `approvals` table.
- No upload here. The Publisher picks up `approved` clips.

### Contract with other modules (migration `003_approvals.sql`)
New columns on `clips`: `state` (default `found`), `state_changed_at`, `context_line`, `hooks_json` (JSON array of 3 strings), `approval_sent_at`, `last_error`. The Writer fills `context_line` and `hooks_json`; QC sets `state='qc_passed'` and `file_path`. The Editor must re-render clips in `needs_rerender` using the new `hook_text`, then send them back to `qc_passed` and clear `approval_sent_at` so Lucas sees the new version.

### Create the bot
1. In Telegram open **@BotFather** → `/newbot` → pick a name and username → copy the token.
2. Send any message to your new bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `message.chat.id`. (Or message **@userinfobot**.) That is your chat id.
3. Put both in `/opt/clipper/.env` (never in git):
```
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ALLOWED_CHAT_ID=123456789
CLIPPER_DB=/opt/clipper/clipper.db   # optional, this is the default
```

### Run
```
pip install -r clipper/requirements.txt
cd clipper/publisher && python approve_bot.py
```
Long polling, no public IP needed.

### systemd service (`/etc/systemd/system/clipper-approve.service`)
```
[Unit]
Description=Clipper Telegram approval bot
After=network-online.target

[Service]
WorkingDirectory=/opt/clipper/app/clipper/publisher
EnvironmentFile=/opt/clipper/.env
ExecStart=/opt/clipper/venv/bin/python approve_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Then `sudo systemctl enable --now clipper-approve`. Adjust the paths to match `infra/setup.sh`.

### Tests
`pip install -r clipper/requirements-dev.txt && pytest clipper/publisher` (offline, Telegram mocked).

## Upload (not built)
**Constraints (D21):** uploads have their own quota bucket (~100/day, ~100 units each). Unverified projects may upload public now; confirm with one test upload. If private-only, request the audit and upload by phone meanwhile.

**Next:** Google Cloud project, OAuth, `upload.py` (picks up `approved` clips).
