# Clipper status (live)

**Read this first in any new PRM chat.** It says what is running right now, what is waiting and who it waits on. Strategy: [`STRATEGY.md`](STRATEGY.md) · decisions: [`DECISIONS.md`](DECISIONS.md) · the box and how to get a shell: [`../infra/VM.md`](../infra/VM.md).
**Rule:** any session that changes what runs, what's next or who something waits on updates this file in the same PR.

_Last updated: 2026-10-27 13:00 UTC_

## Running now (VM `prm-clipper` on moon)
| Piece | State |
|---|---|
| Pipeline (`clipper-pipeline.timer`, every 20 min) | ✅ live: formats → metrics → **market scan (daily, D48; top 8 streamers re-scanned every 6 h, D54)** → **streamer styles (daily, D49)** → **same moments as the top clippers (after each scan, D54)** → radar (**off since D60: remakes only**) → capture → Writer → render → QC → re-render → visual check (D47) |
| Remake engine (`clipper-remake.timer`, next run 5 min after the last ends (D63; was 30 min), D58) | ✅ live since 2026-10-21, **identical-remake engine (D61, PR #112) live since 2026-10-22 00:30 UTC** (caption look measured + fitted per clipper, remembered per channel in `/opt/clipper/remake/_styles/`; since D62 the caption word colours are ours (multicolour) and the caption gate ignores colour; per-frame colour effects; framing aligned; frame sync checked; match % in Telegram). Remakes wait for Lucas's ✅ (`AUTO_POST_REMAKES` unset): one popping clipper Short per run (most views/hour × chance its footage is found first: IShowSpeed 1 of 47, Kai Cenat 12 of 33, iboclips 6 of 6 on 2026-10-28) rebuilt from the streamer's Twitch VOD → `edited` clip → QC → visual check → Telegram/auto-post. **The only source of Shorts (D60)**; our own cuts are off. Skips streamers with no Twitch VOD (Speed, Ludwig: YouTube streams). Downloads the Short with the cookie file `/opt/clipper/youtube_cookies.txt` (D59); the VM has IPv6 since 2026-10-21 (some YouTube servers only answer on IPv6) |
| Channel | ✅ **Peakz Recaps**, `@Peakz.Recaps` (`UCwGp40UYVYzw1GkyZ7_lOpg`), profile picture + banner up |
| Telegram bot `@PRM_Clips_BOT` | ✅ live, **auto-post on** (`AUTO_POST=1`, D44): each new clip is approved by itself and Lucas gets an FYI with **🛑 Stop** (works until the next upload slot). Music-risk clips and clips that fail the visual check (with the reason) still wait for ✅ Post / ❌ Kill. Re-renders first if made in an older style |
| Uploader (`clipper-upload.timer`) | ✅ live: approved clips go up **as soon as approved**, any hour, ≥30 min apart, max 6/day (D52) (`.env`: UTC window 00:00–23:59) |
| Metrics (`metrics` stage of every pass) | ✅ views/likes/comments per Short hourly → `post_metrics`; **owner analytics every 6 h (D53): stayed % (engaged/views) + watched % → `post_analytics`**; Telegram `/stats` + daily recap 23:00 Asunción |
| Trend Scout (GitHub Actions, 10:30 UTC daily) | ✅ report issue + `trends` branch: `library.md` (titles/hooks), `style.json` (caption style), `hashtags.json` (D46). Publishing to `trends` was broken 2026-10-17 → 10-20 (generated files blocked the branch switch); fixed in the trends-publish PR |
| Keys in `/opt/clipper/.env` | ✅ Anthropic, YouTube API key + upload token (OAuth app published), Twitch, Telegram |
| Access for Claude | ✅ SSH from moon's local shell, `/vm` on issue #58, scoped sudo for restarting `clipper-*` services |

## The format today (follow the market, D36)
- **Remakes (D58, from 2026-10-21):** every Short becomes a frame-faithful remake of a popping clipper Short, rebuilt from the streamer's own VOD (their seconds, cuts, crops/zooms/pans, wide-over-blur, flashes, captions, grade, aspect, audio cut timing; our title; no music). Proof of concept: Ron date remake v2 (study scripts in `/opt/clipper/study/ron-date/` on the VM). Until the remake engine is live, the pipeline below keeps running.
- **Streamers:** picked by **Shorts demand** (what's popping about them on Shorts in 48 h, any channel) × fresh footage (D48). 2026-10-20: Jynxzi, Lacy, Stable Ronaldo, CaseOh on top; Speed/Kai have the most demand but no footage we can get.
- **Moments (D54, Lucas: "same clips"):** the moments the top clippers' Shorts are popping with go first: each popping Short is matched to the streamer's own Twitch/Kick clip of that moment (Haiku on titles + times). Our title paraphrases theirs with synonyms (never identical); cut to their length. One moment is never posted twice.
- **Sources:** Twitch clips + **Kick clips** (D45): Heat Index picks from the ~36-streamer watchlist (Adin Ross, N3on, Clavicular, Ice Poseidon on Kick; xQc on both). YouTube footage blocked (YouTube answers 429 to the home IP), see #64.
- **Length (D51, Lucas: "always follow the top clippers"):** the length the top clippers post for that streamer right now (median of their popping Shorts; 2026-10-20: Lacy 19 s, Kai 20 s, Stable Ronaldo 26 s, CaseOh 27 s, Jynxzi 39 s). A longer clip is cut to its best part of that length (setup + payoff); never longer than the source; ≤60 s.
- **Look (D56, always the clipper's structure):** the layout of the clipper's Short of that moment, else how the top clippers frame that streamer: full-bleed 9:16 that follows the people, their wide shot over a blurred copy (`fit`), or facecam on top + gameplay below. Captions per today's `style.json` (2026-10-19: ALL CAPS, white, black outline, 3 words, highlight colour rotating cyan/lime/pink per clip). Hook only for 2.5 s. No context-line banner.
- **Text:** Writer (Haiku 5.5) follows today's format library: short casual titles with emoji, hook templates.
- **On screen:** plain words only (no emoji), `@Peakz.Recaps` watermark low-centre like NexxoRecaps (D46). **Per streamer, the look of their popping Shorts** (D49): font family (most use a condensed font like Anton), keyword colour or plain white, header box, words per line.
- **Hashtags:** daily from the top Shorts (`hashtags.json`): streamer tag at the end of the title, popping tags + #shorts in the description (D46).

## Clips so far
| Date | Made | Approved | Published | Notes |
|---|---|---|---|---|
| 2026-10-19 | 5 | 4 (xQc, Valkyrae, emiru, Lacy) | 1 so far: **first Short live 19:20 UTC** ([Valkyrae](https://youtube.com/shorts/BqOQ8cAeRMo)); the other 3 every 30 min | Sykkuno's clip still waiting (his own burned-in captions double ours → kill) |

Check live: `sqlite3 /opt/clipper/db/clip.db "select id,state,title from clips"` on the VM.

## Waiting on Lucas
- After merging the refine PR: `sudo cp /opt/clipper/repo/clipper/infra/systemd/clipper-remake.service /etc/systemd/system/ && sudo systemctl daemon-reload` (75 min stop instead of 60).
- **Edit the description of [GSiO8GujwEs](https://youtube.com/shorts/GSiO8GujwEs) in YouTube Studio:** delete the first line (`Remake of : "Jason And Ron…"`). The upload token only has the `youtube.upload` scope, so Claude can't edit it.
- AdSense signup + W-8BEN.
- Decision on YouTube footage (#64). Legit routes: Whop official clipping campaigns (send campaign links) or YouTube heat via the official API (#70).

## HQ session playbook (Lucas 2026-10-27: precision/quality first, fewer and shorter sessions)
- **One session = one issue** (`remake-precision` label: #121 lost frames, #122 shake/zoom+effects, #123 freeze/ramps,
  #124 caption size/pop per word, #125 glow captions; #126 match % vs views). Medium thinking.
- **Measure, don't guess:** sandbox on the VM, never the live engine: `/opt/clipper/work/idtest` (`repo2` = branch
  checkout, `clip.db` copy, `recap.sh <short_id> <streamer> <published> pix "<channel>"` re-runs one Short;
  `ab.sh <short_id>` makes the original|remake video). Example Shorts per issue are in each issue body.
- **Keep output small:** grep the `[remake]` lines, look at one frame grid, not whole logs. Report before/after %.
- Ship as a PR; Lucas merges; deploy = `git pull` on the VM (+ bot restart if `publisher/` changed).

## Next for Claude
- **Ops (2026-10-27):** quality gate (picture ≥ 80 %, captions ≥ 70 %, env `REMAKE_MIN_*`) and Telegram health alerts (disk, cookies, failing/idle remakes) run every pipeline pass. Precision work is queued as GitHub issues (label `remake-precision`); add `agent` to one to start it.
- **Learning loop:** after 2-3 weeks compare each remake's match % (render sidecar json) with its views: is more precision worth it, or is moment picking the lever?
- **Remake engine (D58, D60, D61):** 2026-10-21: the two Agent00 remakes (clips 24, 25) came out with the wrong caption look and were deleted by Lucas (state `removed`). D61 build: caption look measured per clipper (68 fonts by glyph shape, size, box, colours, position, pop), caption states frame-exact from their pixels, per-frame colour effects, video resynced to their pixels, match score per remake. Next: picture misses where the map loses frames (fast cuts, punch-in zooms), 4K export, hook edits for remakes. Ludwig `NlN2y6YvX0E` used both attempts; reset `attempts` to retry. Stacked / overlay layouts (facecam + gameplay) are remade since #130 instead of skipped. Source search (#131): a Short is also searched in partners' streams (Agent00's Shorts came from Kai Cenat's), only the stream before it went up, and given up after 10 min (a miss cost up to an hour); most skips are still Shorts that aren't in any stream we search (0 snippets of 8). See `clipper/remake/README.md`.
- Day-3 check (D53): views per Short + stayed % → keep/raise 6/day if stayed ≥ 60 %, cut to 3 strong slots if 0-view Shorts persist.
- Check the first same-moment matches (`select streamer, short_title, clip_id, confidence from moment_matches`) against the clips: tune `MIN_CONF` if a match is wrong.
- Feed views per streamer / format back into the Heat Index and the Writer (learning loop).

## On hold (until the first Shorts perform, D35)
#70 YouTube streamers (Speed) source · #45 · #28.
