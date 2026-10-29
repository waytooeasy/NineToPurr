# Studio status (live): Nine to Purr

**Read this first in any Studio session.** What runs, what waits, on whom. Strategy: [`STRATEGY.md`](STRATEGY.md) · decisions: [`DECISIONS.md`](DECISIONS.md) · market: [`MARKET.md`](MARKET.md) · cast: [`../series/nine-to-purr/BIBLE.md`](../series/nine-to-purr/BIBLE.md).
**Rule:** any PR that changes what runs, what's next or who something waits on updates this file.

_Last updated: 2026-10-29 (go: final plan PR)_

## Running now
- **Go given 2026-10-29** (S7). Nothing of Studio runs yet; no spend yet.
- Clipper: remake engine paused by HQ (`REMAKES_PER_DAY=0` in `/opt/clipper/.env`, 19:35 UTC). Pipeline, upload timers and the clipper bot still run until Lucas pastes setup step 1.
- Pilot tool on the VM: `~/studio-pilot/pilot.py` (user `prm`; throwaway, not the pipeline): `models`, `refs`, `omni-test`, `spent`. Reads keys from `/opt/clipper/.env`, logs every paid call to `ledger.jsonl`, hard cap $5 (`PILOT_MAX_USD`), sends previews to Telegram. Output: `/opt/studio/series/nine-to-purr/` once `/opt/studio` exists.

## Waiting on Lucas
[`SETUP.md`](SETUP.md) steps 1–6b: clipper off + `/opt/studio`, delete the Peakz Shorts, rename the channel (Nine to Purr, @NineToPurr), Gemini key in `/opt/clipper/.env`, $30 credit, merge #153, rename the repo to `ninetopurr`.

## Next for Claude
1. After setup: `pilot.py models`, then `pilot.py omni-test` (360p, ~$0.30) to confirm the key, billing and 9:16 output.
2. Character refs: ~4 Nano Banana candidates each for Mochi, Pearl, Gus (~$0.50) → previews to Telegram → Lucas picks → `/opt/studio/series/nine-to-purr/refs/`.
3. Profile picture + banner from the picked refs.
4. Pilot: 3 episodes from the bible's seeds by hand; look at 360p, finals at 720p → Shorts 1–3 ([`TEST-PLAN.md`](TEST-PLAN.md)).
5. Build issues in this order (each `Depends on` the one before; unpause agents first): `shared/` extraction + `db` → `generator` (ledger + budget guard first) → `radar` → `assembler` → `qc` → `publisher` (bot + upload, reusing the clipper's bot token and upload token) → `room` → `analyst`. Until a module lands, HQ does its step by hand.
6. After Lucas renames the repo to `waytooeasy/ninetopurr`: check the VM shell runner still answers; update links in `CLAUDE.md`, `clipper/infra/VM.md` and the project docs.

## Shorts so far
| Date | Made | Posted | Notes |
|---|---|---|---|
| — | — | — | — |
