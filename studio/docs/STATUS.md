# Studio status (live)

**Read this first in any Studio session.** What runs, what waits, on whom. Strategy: [`STRATEGY.md`](STRATEGY.md) · decisions: [`DECISIONS.md`](DECISIONS.md) · market: [`MARKET.md`](MARKET.md).
**Rule:** any PR that changes what runs, what's next or who something waits on updates this file.

_Last updated: 2026-10-29 (design PR)_

## Running now
Nothing. Design only (S1). No keys, no channel, no spend.

## Waiting on Lucas
1. **Go** (or changes to the plan).
2. Cast pick A/B/C ([`../series/CAST-OPTIONS.md`](../series/CAST-OPTIONS.md)) and voice default (wordless or narrator).
3. [`SETUP.md`](SETUP.md) steps 2–9 (Peakz private, Google Cloud project, Gemini key, channel, tokens, bot, spend limit, AdSense).

## Next for Claude (after go)
1. Stop the clipper timers (clipper D66); note it in `clipper/docs/STATUS.md`.
2. Write `series/<slug>/BIBLE.md`; ref candidates → Lucas picks.
3. One Omni test at 360p to confirm the key and 9:16 output (~$0.30).
4. Pilot: 3 episodes by hand, look iterated at 360p, finals at 720p → Shorts 1–3 ([`TEST-PLAN.md`](TEST-PLAN.md)).
5. Open build issues in this order (each `Depends on` the one before): `shared/` extraction + `db` → `generator` (ledger + budget guard first) → `radar` → `assembler` → `qc` → `publisher` (bot + upload) → `room` → `analyst`. Until a module lands, HQ does its step by hand.

## Shorts so far
| Date | Made | Posted | Notes |
|---|---|---|---|
| — | — | — | — |
