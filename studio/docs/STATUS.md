# Studio status (live): Nine to Purr

**Read this first in any Studio session.** What runs, what waits, on whom. Strategy: [`STRATEGY.md`](STRATEGY.md) · decisions: [`DECISIONS.md`](DECISIONS.md) · market: [`MARKET.md`](MARKET.md) · cast: [`../series/nine-to-purr/BIBLE.md`](../series/nine-to-purr/BIBLE.md).
**Rule:** any PR that changes what runs, what's next or who something waits on updates this file.

_Last updated: 2026-11-16 18:15 UTC (repo renamed; still waiting on the Gemini key and credit)_

## Running now
- **Go given 2026-10-29** (S7). No Studio spend yet.
- **Clipper fully off** (D67): `clipper-remake/pipeline/upload` timers and `clipper-approve-bot` disabled and inactive (checked 20:20 UTC).
- **Channel:** "Nine to Purr", handle `@ninetopurr` (`UCwGp40UYVYzw1GkyZ7_lOpg`), 0 videos (Peakz Shorts deleted), 0 subs. Description set; its last line ("New episode every day. Animated with AI.") is missing.
- **Pilot tool v2 on the VM:** `~/studio-pilot/pilot.py`, run with `/opt/clipper/venv/bin/python` (user `prm`; throwaway, not the pipeline): `models`, `omni-test`, `refs`, `pick`, `episode` (Omni shots with character refs → ffmpeg assembly: 1080×1920, Anton captions, −14 LUFS, black/freeze QC → Telegram), `upload` (private or scheduled), `spent`. Every paid call goes to `ledger.jsonl`; hard cap $15 (`PILOT_MAX_USD`). Each episode keeps a sidecar (prompts, refs, takes, cost): the YPP appeal pack.
- **Pilot storyboards** in `/opt/studio/series/nine-to-purr/episodes/`: ep001 "He slept through the meeting and still got promoted", ep002 "The printer only respects the lazy coworker", ep003 "Me at 5:00 PM vs my overachiever coworker". Font: `/opt/studio/fonts/Anton-Regular.ttf`.

## Waiting on Lucas
1. [`SETUP.md`](SETUP.md) step 4: Gemini key into `/opt/clipper/.env` (checked 2026-11-16: not there).
2. Step 5: $30 prepaid credit in AI Studio.

Done since Oct 29: repo renamed to `waytooeasy/NineToPurr` (old links redirect; the VM shell runner still answers; the VM's git remote still uses the old URL and works through the redirect).

**Clock:** the test was planned for Nov 1–14 and hasn't started. Starting Nov 17 puts the Day-14 call at ~Dec 1 and leaves ~6 weeks of sprint before a mid-January YPP application instead of ~8. Pilot spend so far: $0.

## Next for Claude
1. After steps 4–5: `pilot.py models`, then `pilot.py omni-test` (360p, ~$0.30) to confirm the key, billing and 9:16 output.
2. `pilot.py refs` (4 candidates each for Mochi, Pearl, Gus, ~$0.50) → Telegram → Lucas picks → `pilot.py pick Mochi=… Pearl=… Gus=…`.
3. Profile picture + banner from the picked refs.
4. `pilot.py episode …/ep001.json --res 360p` (~$0.75 each) → look check with Lucas → `--res 720p` (~$2.50 each) → `upload --at` 15:00 Asunción. Shorts 1–3 ([`TEST-PLAN.md`](TEST-PLAN.md)).
5. Build issues in this order (each `Depends on` the one before; unpause agents first): `shared/` extraction + `db` → `generator` (ledger + budget guard first) → `radar` → `assembler` → `qc` → `publisher` (bot + upload, reusing the clipper's bot token and upload token) → `room` → `analyst`. Until a module lands, HQ does its step by hand.
6. Repo rename follow-up: runner checked (works). Still to do: point old `waytooeasy/PRM` links and the VM's git remote at `waytooeasy/NineToPurr` (cosmetic; redirects work).

## Shorts so far
| Date | Made | Posted | Notes |
|---|---|---|---|
| — | — | — | — |
