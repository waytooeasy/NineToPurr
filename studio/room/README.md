# Writers' room (design only)

**Status:** not built. Build order 7. During the pilot HQ writes premises by hand with the same rules.

**Scope:** every morning, premises inside today's popping formats; after the pick, the script, storyboard and metadata.

| | |
|---|---|
| **In** | `series/<slug>/BIBLE.md` (prompt-cached), `waves.json`, `library.md`, the last 14 days of results, the continuity log, past premises (similarity) |
| **Out** | 10 premises → self-critique → top 5 to Telegram (`premises`). For the pick: `episodes` + `shots` rows: per shot the Omni prompt (subject, action beats, camera, SFX, "no dialogue", the bible's style line), ref order, first-frame plan, seconds; on-screen text cards with times; title, description, hashtags; cost estimate |
| **Engine** | Claude Sonnet 5.5, Lucas's existing API key (S8) |
| **Runs** | 08:00 Asunción; script right after the pick (or the 11:00 auto-pick) |
| **Cost** | cents/day |

**Rules:** one new story per Short (similarity < 0.85 vs the last 30); hook in the first 1.5 s; payoff in the last 2–3 s; adult-life topics; no real people, brands, kids, distress or sexual tropes; titles follow today's patterns but are always our own words; each premise says why now (which wave, its numbers).
