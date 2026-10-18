# Readiness

Is the clipper ready to run on the VM? Status after issue #48. ✅ = built and tested offline, ❌ = missing, ⚠️ = built, but never run against the real service.

**Proof it hangs together:** `clipper/tests/test_e2e_offline.py` (runs in CI). Fresh DB via `db/migrate.py` → one pipeline pass with a Twitch and a YouTube source (Twitch API, yt-dlp, Whisper and the LLM mocked; real ffmpeg on a tiny synthetic video) → `qc_passed` → bot approval → `approved` → `upload.run_once` with a fake uploader → `published`. It found no glue bugs.

## Modules
| Module | State | Notes |
|---|---|---|
| `db` (schema, migrations, `migrate.py`) | ✅ | Fresh DB and re-run (no-op) tested. |
| `radar` (Heat Index, Twitch clips, YouTube VOD moments, capture) | ✅ ⚠️ | Offline-tested. Real Twitch and yt-dlp not exercised. Watchlist Twitch logins are best guesses. |
| `editor` (Writer, Whisper, render, QC, re-render) | ✅ ⚠️ | Real Haiku call and real Whisper not exercised. Re-render of a YouTube clip cuts the wrong window (see risks, needs HQ). |
| `publisher` approval bot | ✅ ⚠️ | Logic tested with a fake Telegram; no real bot yet. |
| `publisher` upload | ✅ ⚠️ | Fake uploader only. Real YouTube API never called; D21 test upload still to do. |
| `run_pipeline.py` + systemd units | ✅ | Tested with injected stages and the flock. Units not yet started on the VM. |
| `infra/setup.sh` | ⚠️ | Not yet run on the real VM. |
| `analyst`: Trend Scout | ✅ | Runs in GitHub Actions (HQ-owned). |
| `analyst`: metrics puller (`post_metrics`) | ❌ | Not built. Needed for the Phase 0 gate (D11) and for Heat saturation feedback. |
| `analyst`: daily Analyst (Sonnet) | ❌ | Not built. |
| Chat-spike radar, perceptual duplicate hash, upload retry cap | ❌ | Listed as Next in the module READMEs. |

## First run on the VM
Do these in order. Stop at the first failure.

**On the Windows host (has a browser)**
1. Google Cloud console: create a project, enable **YouTube Data API v3**. OAuth consent screen: External, add the channel's Google account as a test user, then **Publish app** (otherwise refresh tokens die after 7 days). Credentials → OAuth client ID → **Desktop app** → download the JSON.
2. Install Python 3.12, then in a PowerShell window:
   ```
   git clone https://github.com/waytooeasy/prm.git
   cd prm
   pip install requests google-api-python-client google-auth-oauthlib tzdata
   $env:YOUTUBE_CLIENT_SECRET = "C:\path\to\client_secret.json"
   $env:YOUTUBE_TOKEN_FILE    = "C:\path\to\youtube_token.json"
   cd clipper\publisher
   python upload.py --auth
   ```
   A browser opens. Sign in as the **channel's** Google account and allow. The token is written to `YOUTUBE_TOKEN_FILE`.
3. Copy both files to the VM over Tailscale (replace `<vm>` with its Tailscale name, `<user>` with your VM user):
   ```
   scp C:\path\to\client_secret.json C:\path\to\youtube_token.json <user>@<vm>:/tmp/
   ```

**On the VM (Ubuntu 24.04, over Tailscale SSH)**
4. Clone to the required location:
   ```
   sudo mkdir -p /opt/clipper && sudo chown "$USER": /opt/clipper
   git clone https://github.com/waytooeasy/prm.git /opt/clipper/repo
   ```
5. Put the secrets in place (never in git):
   ```
   mv /tmp/client_secret.json /tmp/youtube_token.json /opt/clipper/
   chmod 600 /opt/clipper/client_secret.json /opt/clipper/youtube_token.json
   cp /opt/clipper/repo/clipper/infra/.env.example /opt/clipper/.env && chmod 600 /opt/clipper/.env
   nano /opt/clipper/.env     # fill ANTHROPIC_API_KEY, TWITCH_CLIENT_ID/SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_ID
   ```
   Telegram bot token and chat id: see `clipper/publisher/README.md` ("Create the bot"). Anthropic key: Lucas's own account only, with the console spend limit on.
6. Bootstrap (packages, firewall, venv, DB via `db/migrate.py`, Whisper model, systemd units, timers):
   ```
   bash /opt/clipper/repo/clipper/infra/setup.sh
   ```
7. Check the DB and the schedule, without any API call:
   ```
   sqlite3 /opt/clipper/db/clip.db "select version from schema_migrations order by version"
   cd /opt/clipper/repo/clipper/publisher && /opt/clipper/venv/bin/python upload.py --dry-run
   systemctl list-timers 'clipper-*'
   ```
8. **D21 test upload.** Render or copy any short mp4, then:
   ```
   cd /opt/clipper/repo/clipper/publisher
   set -a; . /opt/clipper/.env; set +a
   YOUTUBE_CLIENT_SECRET=/opt/clipper/client_secret.json YOUTUBE_TOKEN_FILE=/opt/clipper/youtube_token.json \
     /opt/clipper/venv/bin/python upload.py --test-upload ~/test.mp4 --privacy unlisted
   ```
   Open the link logged out. Then repeat with `--privacy public`. If a public upload is locked/private, the project needs the API audit: tell HQ.
9. Send `/status` to the Telegram bot. It must answer; anyone else gets silence.
10. Run one pipeline pass by hand and watch it:
    ```
    sudo systemctl start clipper-pipeline.service
    journalctl -u clipper-pipeline -n 80 --no-pager
    ```
    Expect a JSON line with a result per stage (`radar`, `capture`, `editor`, `qc`, `rerender`), none starting with `error`. A clip reaching `qc_passed` shows up in Telegram.
11. Approve one clip in Telegram. Within 15 minutes `clipper-upload.timer` uploads it if a slot is due (`journalctl -u clipper-upload -n 50`). Confirm the Short is public.
12. Only now leave it running. Pause anytime: `sudo systemctl stop clipper-pipeline.timer clipper-upload.timer`.

## Top 5 risks
1. **The real YouTube upload has never run.** Visibility (public vs locked), quota and token refresh are untested. If the OAuth app stays in "Testing", the token expires after 7 days and uploads silently stop (alert goes to Telegram, clips stay `approved`). Mitigation: steps 1 and 8.
2. **Live services behave differently from the fixtures.** Twitch clip fields, yt-dlp output (YouTube may bot-block a home IP; yt-dlp is upgraded daily by cron) and Whisper on the VM CPU were only mocked. Expect a first-day round of small fixes. Mitigation: step 10, read the logs.
3. **YouTube re-render is wrong.** `editor/rerender.py` cuts the downloaded window file with absolute `clips.start_s/end_s`, so *Edit hook* on a YouTube-VOD clip renders the wrong moment. Twitch clips are fine. Contract change, needs HQ (already flagged in `radar/README.md`). Until decided: use ✅ or ❌ on YouTube clips, not ✏️.
4. **Reused-content and quality rules (D7).** Nothing automated checks that a Short really has our angle, and QC duplicate detection is an exact file hash only (no perceptual hash). Lucas approving every Short (D10) is the only real guard. Writer quality and cost per clip are untested on live transcripts (`llm_usage` will show cost).
5. **The home VM is a single point of failure.** If Windows reboots or the VM does not auto-start, nothing runs; a crash between `videos.insert` and the DB commit would upload a clip twice (accepted, documented); a permanently broken `approved` clip is retried last on every pass (no retry cap yet). No metrics puller means the Phase 0 gate (15 Shorts in 2 weeks, ≥1 over 10K engaged views) is checked by hand in YouTube Studio for now.
