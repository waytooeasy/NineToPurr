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
