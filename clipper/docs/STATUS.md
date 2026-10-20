# Clipper status (live)

**Read this first in any new PRM chat.** It says what is running right now, what is waiting and who it waits on. Strategy: [`STRATEGY.md`](STRATEGY.md) · decisions: [`DECISIONS.md`](DECISIONS.md) · the box and how to get a shell: [`../infra/VM.md`](../infra/VM.md).
**Rule:** any session that changes what runs, what's next or who something waits on updates this file in the same PR.

_Last updated: 2026-10-20 11:30 UTC_

## Running now (VM `prm-clipper` on moon)
| Piece | State |
|---|---|
| Pipeline (`clipper-pipeline.timer`, every 20 min) | ✅ live: formats → metrics → **market scan (daily, D48)** → **streamer styles (daily, D49)** → radar (**paced: 1 clip start every ~4.8 h**) → capture → Writer → render → QC → re-render → visual check (D47) |
| Channel | ✅ **Peakz Recaps**, `@Peakz.Recaps` (`UCwGp40UYVYzw1GkyZ7_lOpg`), profile picture + banner up |
| Telegram bot `@PRM_Clips_BOT` | ✅ live, **auto-post on** (`AUTO_POST=1`, D44): each new clip is approved by itself and Lucas gets an FYI with **🛑 Stop** (works until the next upload slot). Music-risk clips and clips that fail the visual check (with the reason) still wait for ✅ Post / ❌ Kill. Re-renders first if made in an older style |
| Uploader (`clipper-upload.timer`) | ✅ live: approved clips go up **as soon as approved**, any hour, ≥30 min apart, max 5/day (`.env`: UTC window 00:00–23:59) |
| Metrics (`metrics` stage of every pass) | ✅ views/likes/comments per Short hourly → `post_metrics`; Telegram `/stats` + daily recap 23:00 Asunción |
| Trend Scout (GitHub Actions, 10:30 UTC daily) | ✅ report issue + `trends` branch: `library.md` (titles/hooks), `style.json` (caption style), `hashtags.json` (D46). Publishing was broken 2026-10-17 → 10-20, fixed (#79). Runs without YouTube/Twitch keys on GitHub (titles only) until Lucas adds the secrets |
| Keys in `/opt/clipper/.env` | ✅ Anthropic, YouTube API key + upload token (OAuth app published), Twitch, Telegram |
| Access for Claude | ✅ SSH from moon's local shell, `/vm` on issue #58, scoped sudo for restarting `clipper-*` services |

## The format today (follow the market, D36)
- **Streamers:** picked by **Shorts demand** (what's popping about them on Shorts in 48 h, any channel) × fresh footage (D48). 2026-10-20: Jynxzi, Lacy, Stable Ronaldo, CaseOh on top; Speed/Kai have the most demand but no footage we can get.
- **Sources:** Twitch clips + **Kick clips** (D45, live since 2026-10-19): Heat Index picks from the ~36-streamer watchlist (Adin Ross, N3on, Clavicular, Ice Poseidon on Kick; xQc on both). YouTube footage blocked (YouTube answers 429 to the home IP), see #64.
- **Length:** the length viewers chose (the Twitch clip / most-replayed window), trim ≤2 s per end, ≤60 s. Kick clips over 60 s keep their last 60 s.
- **Look:** full-bleed 9:16 centred on the face, or facecam on top + gameplay below (a tiny corner cam over an event goes full-bleed). Captions: global `style.json`, overridden per streamer by `styles.json` (D49). Hook 2.5 s, or a persistent header when that streamer's market uses one. No context-line banner.
- **Text:** Writer (Haiku 5.5) follows today's format library and **today's popping titles about the same streamer** (D48): same moment → paraphrase with synonyms, never a copy. Streamer named as fans write it.
- **On screen:** plain words only (no emoji), `@Peakz.Recaps` watermark low-centre like NexxoRecaps (D46). **Per streamer, the look of their popping Shorts** (D49): font family (most use a condensed font like Anton), keyword colour or plain white, header box, words per line. **Chat / \*action\* captions only if that streamer's clippers use them** (D50; none do today).
- **Hashtags:** daily from the top Shorts (`hashtags.json`): streamer tag at the end of the title, popping tags + #shorts in the description (D46).

## Clips so far
| Date | Made | Approved | Published | Notes |
|---|---|---|---|---|
| 2026-10-19 | 6 | 5 | 5: Valkyrae, xQc, emiru, Lacy, Adin Ross (Kick) | Sykkuno killed (his live captions doubled ours) |
| 2026-10-20 (UTC) | 5 | 5 | 5: Stable Ronaldo, xQc, ExtraEmily, Valkyrae, Sykkuno | all 5 started 00:09 UTC in one burst (pacing fixes this, D48) |

**Views (2026-10-20 09:30 UTC):** 10 Shorts, 95 views; best Valkyrae #1 56. 4 Shorts at 0 views after 9–11 h (xQc #1, emiru, Lacy, Stable Ronaldo): Lacy to check Studio → Content → Restrictions. 60 % "stayed to watch" on the one Lucas checked. The market scan showed why: most slots went to streamers with almost no Shorts audience (Valkyrae ≈400 views/h of demand vs Jynxzi 96k).

Check live: `sqlite3 /opt/clipper/db/clip.db "select id,state,title from clips"` on the VM.

## Waiting on Lucas
- **Merge #84 then #85** (market-driven streamers + pacing + titles/hashtags; per-streamer look + D50). Claude deploys (`migrate.py` for 011, bot restart).
- Studio → Content → Restrictions column for the 0-view Shorts.
- GitHub secrets for the daily Trend Scout: `YOUTUBE_API_KEY`, `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` (same values as `/opt/clipper/.env`). Without them it sees titles only (no lengths, descriptions, discovery).
- AdSense signup + W-8BEN.
- Anthropic Console spend limit.
- Decision on YouTube footage (#64). Legit routes: Whop official clipping campaigns (send campaign links) or YouTube heat via the official API (#70).

## Next for Claude
- Read the first 48 h of views; raise the 5/day cap when views per Short hold up.
- Feed views per streamer / format back into the Heat Index and the Writer (learning loop).
- Engaged views / swipe-away: needs a token with `yt-analytics.readonly` (one re-auth by Lucas).

## On hold (until the first Shorts perform, D35)
#70 YouTube streamers (Speed) source · #45 · #28.
