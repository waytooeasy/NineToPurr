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
