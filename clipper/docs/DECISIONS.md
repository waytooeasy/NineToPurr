# Decisions log

Owned by PRM · 00 HQ. One line per decision. Newest at the bottom. Build sessions read this on start; propose changes via a GitHub issue labeled `needs-hq`.

| # | Date | Decision | Why |
|---|---|---|---|
| D1 | 2026-10-15 | Own YouTube Shorts channel of streamer clips; no ties to streamers; paid by YouTube ads; English/US | Lucas's model |
| D2 | 2026-10-15 | Runs on home Ubuntu 24.04 VM (VMware), reached over Tailscale; data in `/opt/clipper` | $0 infra, 32 GB PC |
| D3 | 2026-10-16 | One repo `waytooeasy/prm`, one folder per project; strategy in `clipper/docs/` | Shared memory for all sessions |
| D4 | 2026-10-16 | No Anthropic API; never a second account. Claude builds the code; at most 1–3 `claude -p` jobs/day via official CLI + `setup-token` | Terms + account safety |
| D5 | 2026-10-16 | Per-clip LLM = **Gemini 3.1 Flash-Lite** (paid tier, $50 hard budget cap) | Cents/month, separate from Claude |
| D6 | 2026-10-16 | **One** multi-streamer channel; Kai first; creator list in config | Feb 2027 10M/90d floor is per channel; Kai saturated + irregular |
| D7 | 2026-10-16 | Every clip gets a context line + storytelling captions; no raw re-uploads | Reused-content rules; Oct 2 2026 reach cut |
| D8 | 2026-10-16 | Shorts ≤60 s, 3–5/day, music flag, claims tracked per streamer | Claimed >60 s Shorts blocked; spam policy |
| D9 | 2026-10-16 | Architecture: Python + systemd + SQLite + Telegram approval bot. n8n/agent team unlock at ≥1M engaged views/month | Bottleneck is views, not tooling |
| D10 | 2026-10-16 | Lucas approves every Short (L0) until 2 clean weeks | Quality + "creator's own input" |
| D11 | 2026-10-16 | Phase 0 gate: 15 Shorts in 2 weeks, ≥1 over 10K engaged views, else change format | Validate before automating |
| D12 | 2026-10-16 | Sessions: HQ + one Build session in the repo; module chats optional | Hand-off pain came from 7-chat split |
| D13 | 2026-10-16 | Radar: Twitch Get Clips first, chat spikes later; rank by views/hour; dedupe by VOD + overlapping timestamp; widen to 7 days when thin | Radar session proposal, approved by HQ |
| D14 | 2026-10-16 | Schema changes go in `clipper/db/migrations/NNN_name.sql`; any session may propose, Analyst reviews. Radar gets `002_radar.sql` (`radar_candidates`) | Ownership without blocking |
| D15 | 2026-10-16 | `clip.py --auto` must move from Anthropic SDK to Gemini; hook/context text is the Editor's Writer step; Radar only writes `picks.json` | D4, D5 |
| D16 | 2026-10-16 | Measure engaged views + viewed-vs-swiped-away, not raw views | Shorts count every play |
| D17 | 2026-10-16 | **Anthropic API restored** on Lucas's own account (ban lifted). Supersedes D4. Console spend limit on; key only in GitHub secrets / `/opt/clipper/.env`. Still never a second account. | Ban lifted Oct 16 |
| D18 | 2026-10-16 | Per-clip Writer = **Claude Haiku 5.5** (`claude-haiku-5-5`). Supersedes D5 and the Gemini part of D15. `llm()` stays provider-neutral; Gemini is the fallback. | $0.10/$0.50 per MTok, cheaper than Flash-Lite; one vendor |
| D19 | 2026-10-16 | **Build agents** = Claude GitHub Action (Sonnet 5.5). Lucas starts one by commenting `@claude` on an issue; only his account can trigger it; output is always a PR he merges. | Self-starting build team, no home PC needed |
| D20 | 2026-10-16 | Daily Analyst / Trend Scout run on the API (Sonnet 5.5), not `claude -p` subscription jobs. Runtime n8n/agent team stays gated by D9. | Clean billing, no subscription limits |
| D21 | 2026-10-16 | Publisher: uploads have their own quota bucket (~100/day, ~100 units each). First Publisher task = one API test upload to confirm public visibility. | Research supersedes "6/day, private until audit" |
| D22 | 2026-10-16 | **Clip state machine** lives in `clips.state` (migration 003): `found → captured → drafted → edited → qc_passed → approved/killed/needs_rerender → published → measured`. Shared columns: `context_line`, `hooks_json`, `hook_text` (chosen hook), `approval_sent_at`, `last_error`; `approvals` audit table. Every module reads/writes these. | Accepts PR #9's proposal |
| D23 | 2026-10-16 | **`picks.json` contract:** list of `{source_url, creator, clip_id, start, end}`; `start`/`end` are seconds inside `source_url`. `clip.py` reads `source_url` per pick. | Radar hands Twitch clips, not long VODs |
| D24 | 2026-10-16 | Editor writes Writer output (`model_score`, `context_line`, `hooks_json`, `title`, `music_risk`) to the DB; the CSV is a debug log only. | One source of truth for the Analyst |
| D25 | 2026-10-16 | English/US only for now; Spanish auto-translate dropped. | D1; focus |
| D26 | 2026-10-16 | Migrations run via `clipper/db/migrate.py` (tracks `schema_migrations`), called by `setup.sh` and on every deploy. | Existing VM DBs need 002/003+ |
| D27 | 2026-10-16 | Re-render loop: `needs_rerender` → Editor re-renders with the new `hook_text` → `qc_passed` (clears `approval_sent_at`). QC v1 = ≤60 s, duplicate hash, daily cap 5, `music_risk` → flagged in Telegram. | Closes the approval loop |
| D28 | 2026-10-16 | **Build loop:** agent → PR opens itself → CI → red CI goes back to the agent (max 2) → **Lucas merges (one tap)** → next ready issue starts (`Depends on: #N`). No auto-merge. Repo-scoped token `PRM_BOT_TOKEN`; kill switch `AGENTS_PAUSED=true`. | Automate everything except the merge; code runs on the home PC with keys |
| D29 | 2026-10-16 | Sources = streamers' own footage: Twitch clips **and** Twitch/YouTube live VODs (yt-dlp). Competitor Shorts = format research (Trend Scout), never downloaded or re-uploaded. | Lucas: learn from Shorts channels; their edits are their copyright |
| D30 | 2026-10-16 | Agents: `.claude/agents` (builders per module, reviewer, security) + skills `pr-checklist`, `shorts-format`. Every agent PR gets a reviewer verdict before Lucas merges. Third-party skills only after a read-through. | Quality + one-tap merges |
| D31 | 2026-10-16 | Token budget: build max-turns 25, review 12; Writer uses prompt caching; non-urgent LLM jobs via Batch API (−50%). | Cost |
| D32 | 2026-10-16 | **Creators:** IShowSpeed (YouTube VODs) first, Kai Cenat, CaseOh; weights in config. Kick later. Cap 5/day for 2 weeks, then 8–10/day if 0 strikes and views/Short hold. #27 (YouTube upload) queued; #28 (live capture) parked. | Most clipped Aug 2026: Speed 1.08B, Kai 558M, CaseOh 21.8M (CreatorDB); scale volume on data |
| D33 | 2026-10-16 | **Streamer ranking is daily, not monthly:** Trend Scout ranks streamers every day (clip velocity × Shorts velocity ÷ competition), weekly rollup on Mondays; Radar reads the ranking and auto-adjusts weights / adds new hot streamers. | Lucas: trends move daily; monthly data is too slow |
