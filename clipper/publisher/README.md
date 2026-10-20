# Publisher

**Scope:** (1) the Telegram approval gate (`approve_bot.py`, built); (2) upload approved Shorts to YouTube on a spaced schedule (`upload.py`, built).

**Status:** approval bot built. Upload built (`upload.py`, tests offline; real API not yet exercised, run the D21 test upload).

## Approval bot (D10: Lucas approves every Short)

When a clip reaches `qc_passed`, the bot sends the mp4 (or text only if the file is missing or over 49 MB) with its title and context line.

| Button | Result |
|---|---|
| ✅ Post | `approved` exactly as rendered (the Writer's best hook) |
| ❌ Kill | `killed` |

**Auto-post (`AUTO_POST=1`, D44):** the bot approves each clip itself and sends an FYI "🚀 Auto-posting at the next upload slot" with **🛑 Stop** (`approvals.stop`: approved → killed, only before upload). Clips with `music_risk` still get ✅ Post / ❌ Kill unless `AUTO_POST_MUSIC=1`.

Since 2026-10-19 (Lucas): just Post or Kill. Old messages with ✅ Hook 1/2/3 still work; the edit-hook flow (`e:` button + reply) stays in code but has no button.

- `/stats`: views, views/hour and likes per Short (latest `post_metrics`). A **daily recap** with the same table arrives once a day after 02:00 UTC (23:00 Asunción).
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

**Visual check gate (D47):** the bot only sends a `qc_passed` clip after the pipeline's visual check looked at it (`clips.visual_qa` set; `VISUAL_QA=0` = off). A failed check means no auto-post: the message lists the issues and waits for ✅ Post / ❌ Kill.

## Upload (`upload.py`, built, untested against the real API)
**Constraints (D21):** uploads have their own quota bucket (~100/day, ~100 units each). Unverified projects may upload public now; confirm with one test upload. If private-only, request the audit and upload by phone meanwhile.

**How it works:** the timer runs every 15 min. Each pass computes today's slots; if one is due it uploads the oldest clean `approved` clip via `videos.insert`, writes the `posts` row (video id, url, posted_at, caption) and sets `clips.state='published'` in one transaction.
- Slots (D8): max 5/day, >= 2 h apart, window 19:00-02:00 America/Asuncion (crosses midnight; at 01:00 the window that began yesterday is current). Gotcha: a 7 h window with a 2 h gap fits only 4 slots. For 5 set `UPLOAD_WINDOW_END=03:00`.
- Title = `clips.title`, else `hook_text` (<= 100 chars). Description = `context_line` + `#Shorts`. Tags include `#Shorts` + `topic_tags`. Category Gaming (20).
- **Market hashtags (`hashtags.py`, Lucas 2026-10-19):** from `$CLIPPER_HASHTAGS` (hashtag scout): the streamer's tag at the end of the title when most top Shorts carry one (NexxoRecaps: `... 😭 #ishowspeed`) and the Writer didn't already; description = story line + streamer tag + today's popping generic tags + #shorts; tags = streamer name + market keywords. Only the clip's own streamer is tagged. Kick clips get `#kick` instead of `#twitch`. No file → default (streamer tag in title, #shorts). **Per streamer (D48):** the hashtags the popping Shorts about this streamer use (market scan, 2+ channels, e.g. Jynxzi → `#jynxzi #r6`) come right after the streamer tag; at most 6 hashtags in the description.
- Idempotent: a clip that already has a `posts` row is only marked published, never re-uploaded. Account row (`youtube`, handle `YOUTUBE_CHANNEL_HANDLE`) is created on first upload.
- Quota (403 `quotaExceeded`/`uploadLimitExceeded`): `last_error` = `quota: ...`, Telegram alert, no more uploads until the next local day. Clip stays `approved`.
- Other errors (missing file, API failure): `last_error` + Telegram alert, clip stays `approved`, one attempt per pass, and clips with an error sort after clean ones so they never block the queue. There is no retry cap yet: a permanently broken clip is retried last on every pass (kill it in the DB or re-approve to clear).
- Known risk: if the process dies between `videos.insert` returning and the DB commit, the next pass uploads that clip again (duplicate video). Window is milliseconds; accepted for now.

Env (all optional): `CLIPPER_DB`, `YOUTUBE_CLIENT_SECRET` (default `/opt/clipper/client_secret.json`), `YOUTUBE_TOKEN_FILE` (default `/opt/clipper/youtube_token.json`), `YOUTUBE_CHANNEL_HANDLE`, `YOUTUBE_CATEGORY_ID` (20), `UPLOAD_PRIVACY` (public), `UPLOAD_TZ`, `UPLOAD_WINDOW_START`, `UPLOAD_WINDOW_END`, `UPLOAD_MAX_PER_DAY` (5), `UPLOAD_MIN_GAP_HOURS` (2), plus `TELEGRAM_BOT_TOKEN` / `TELEGRAM_ALLOWED_CHAT_ID` for alerts.

### One-time OAuth setup
1. console.cloud.google.com: create a project, **APIs & Services -> Library -> YouTube Data API v3 -> Enable**.
2. **OAuth consent screen**: External, add your Google account as a test user.
3. **Credentials -> Create credentials -> OAuth client ID -> Desktop app**. Download the JSON, save as `/opt/clipper/client_secret.json` (never in git).
4. Run `python upload.py --auth` on a machine with a browser (log in with the channel's Google account). It writes the token to `YOUTUBE_TOKEN_FILE`. For the headless VM, run it on your PC with `YOUTUBE_CLIENT_SECRET`/`YOUTUBE_TOKEN_FILE` pointing at local files, then `scp` the token to `/opt/clipper/youtube_token.json` (chmod 600). It refreshes itself afterwards.
5. Note: while the consent screen is in "Testing", Google expires refresh tokens after 7 days. Publish the app (still unverified is fine for own use) so the token lasts.

### D21 test upload (do this first)
```
cd clipper/publisher
python upload.py --test-upload some_short.mp4 --privacy unlisted   # then public
```
Open the printed link logged out. If a public upload shows as locked/private, the project needs the API audit; upload by phone meanwhile and tell HQ.

### Run / inspect
```
python upload.py --dry-run     # today's slots and which clip goes where, no API, no writes
python upload.py               # one pass (what the timer runs)
```

### systemd
```
sudo cp clipper/infra/systemd/clipper-upload.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now clipper-upload.timer
```

**Next:** run the D21 test upload; then watch the first live day (`journalctl -u clipper-upload`). Later: retry cap for broken clips, shift slots by Heat Index (D33), pull metrics into `post_metrics`.
