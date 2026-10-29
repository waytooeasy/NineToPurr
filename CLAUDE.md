# PRM — instructions for Claude

PRM = Puro Rico o Muerto. Lucas's money projects. One folder per project.

**Read first, every session:** the `docs/STATUS.md` of the project you touch (what runs now), then its `STRATEGY.md` and `DECISIONS.md`. Clipper: `clipper/docs/`. Studio: `studio/docs/`.

## Studio (design only, 2026-10-29)
- Original AI character Shorts on a new channel: a recurring animal cast living adult human life, playing whatever format is popping in AI Shorts today. **Copy formats, never content (S2).**
- **No Studio code and no spend until Lucas says go (S1).** Until then only HQ edits `studio/`.
- Separate stack on the same VM: `/opt/studio`, own Google Cloud project, channel, Telegram bot, budget cap (S3). Tools: **Claude first** for all writing and thinking (Sonnet 5.5) and picture QC on frames (Haiku 5.5); Gemini only where Claude can't: Omni 1.1 Flash (video), Nano Banana 2 Lite (refs), TTS (voice), 3.8 Flash (watching Shorts, motion/sound QC) (S4, S7). Format rules: `.claude/skills/studio-format`.

## Clipper (active)
- One YouTube Shorts channel, multi-streamer brand; the Heat Index picks streamers daily. No ties to streamers. Paid by YouTube Shorts ads.
- **Follow the market (D36):** copy what works for the top clip channels today; don't invent rules. Every clip: hook + story captions in today's style + our title. **Structure = the clipper's (D56):** layout (full / wide shot over blur / face-on-top stack), captions, length and title are copied from the clippers of that moment or streamer, never our own invention. **Remakes (D58):** every Short is a frame-faithful remake of a popping clipper Short, rebuilt from the streamer's own VOD (their seconds, cuts, zooms, captions, look); our title, no music, never their pixels. Market length ≤60 s. Max 5/day, posted as soon as Lucas taps ✅ Post. Streamer audio, no raw re-uploads.
- Stack: Python + systemd timers + SQLite + Telegram approval bot. Per-clip LLM = **Claude Haiku 5.5** (Anthropic API); daily Analyst = Sonnet 5.5. Runtime n8n/agent team only after the gate in STRATEGY.md.
- **Anthropic API = Lucas's own account only. Never a second account.** `ANTHROPIC_API_KEY` lives in GitHub secrets and `/opt/clipper/.env`, never in git or logs.
- Build agents run via the Claude GitHub Action: Lucas comments `@claude` on an issue → agent builds → opens a PR. Agents never merge, never edit `.github/workflows/`, never touch secrets.
- Runs on a home Ubuntu 24.04 VM (`prm-clipper`, Hyper-V on Lucas's Win 11 PC `moon`), reached over Tailscale. Data in `/opt/clipper`, never in git.
- **Need a shell on the VM?** Read `clipper/infra/VM.md` first: SSH from the local shell on moon, or comment `/vm` on issue #58 (self-hosted runner). Never use the INFOCENTER work laptop.

## Sessions
| Session | Owns |
|---|---|
| **PRM · 00 HQ** | Strategy, numbers, gates, `STRATEGY.md`, `DECISIONS.md` |
| **PRM · Build** | All code in `clipper/` (radar, editor, publisher, analyst, db, infra) |
| Module sessions (optional) | One folder each, same rules |

## Rules
- **Exactly one HQ:** the chat named "PRM · 00 HQ". No other chat or agent edits any project's `STRATEGY.md` or `DECISIONS.md`, or `CLAUDE.md`, or pushes to `hq/*` branches. If you're not HQ and something needs a decision, open a `needs-hq` issue.
- Work on a branch; open a PR. Never push to `main`.
- Anything that changes strategy or another module's contract → open a GitHub issue labeled `needs-hq` and keep building around it.
- Schema changes only as `clipper/db/migrations/NNN_name.sql`.
- Each module keeps a `README.md`: scope, status, how to run, next step. Update it before ending a session.
- Never commit secrets (`.env`, OAuth tokens, `client_secret*.json`) or media/DB files.
- Never add detection-evasion edits (speed-up, pitch shift, mirroring, heavy filters).
- **Build loop:** agent finishes → PR opens itself → CI → if red, the agent is asked to fix it (max 2) → **Lucas merges** → the next ready issue starts. Keep CI green; never weaken or skip tests.
- Issues run in order via the agent queue. Put `Depends on: #N` at the top of an issue body to sequence it. Labels: `agent` (queue it), `hold` (stop), `in-progress` (running), `needs-hq` (decision needed).
- Every PR: tests for new code (`pytest`, sample data, no network), module README updated, `DECISIONS.md` untouched (HQ only).
- Sources = streamers' own footage (Twitch clips, Twitch/YouTube live VODs). Competitor Shorts: download them to **study and imitate** their edit (which parts of the stream, cuts, zooms, captions, layout), **never re-upload or reuse their footage** (D57). See `.claude/skills/shorts-format`.
- Subagents in `.claude/agents/` (builder-radar/editor/publisher, reviewer, security). Read only what the task needs to save tokens.
- Lucas wants short, direct answers and the whole system in mind; ask when unsure instead of assuming.
- **Keep each project's `docs/STATUS.md` current:** if your PR changes what runs, what's next or who something waits on, update it in the same PR.
