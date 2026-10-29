# Nine to Purr — strategy (v2, 2026-10-29)

Owner: **PRM · 00 HQ**. Decisions: [`DECISIONS.md`](DECISIONS.md) · live state: [`STATUS.md`](STATUS.md) · evidence: [`MARKET.md`](MARKET.md) · cast: [`../series/nine-to-purr/BIBLE.md`](../series/nine-to-purr/BIBLE.md). Mirrored in the Claude project doc `claude/11-studio-plan.md` (the repo wins).

## Focal point
**One AI cat office comedy on YouTube, "Nine to Purr" (@NineToPurr). One goal: get into the YouTube Partner Program before Feb 1, 2027** (S7).

## The model
- **Show:** three coworkers at Clawporate Inc.: Mochi (lazy orange cat who somehow wins), Pearl (overachiever white cat who somehow loses), Gus (pigeon boss who calls a meeting about it). Comedy, adult work life, never sad stories (S9).
- **Shorts, 20–40 s:** one situation, a turn, a payoff in the last 2–3 s. Wordless cast, sound effects, on-screen text. Formats follow what's popping in AI Shorts (radar, S2).
- **Channel:** Peakz Recaps renamed to Nine to Purr; same keys, project, upload token and bot (S8). YouTube only until a hit (S10).
- **Money:** YouTube Partner Program (Shorts pool + long-form ads), then brand deals and merch once a character has an audience.
- **Lucas:** picks the day's premise and taps ✅ in Telegram (~5 min/day).

## Why
| Fact | Number |
|---|---|
| AI cats are YouTube's biggest live lane | Cat Ai Network ~73M views and ~203k subs in the last 30 days (tracker); Batysyr 100M views in a month from 20 AI cat videos; Cat channel 91 grew to 2M subs after switching to AI cats |
| Generic AI cat channels die | CatVerse Studio: 94 Shorts → 26 subs. Meowffice (office cats, our concept): 399 six-second vibe clips, recent ones ~15 views |
| Rivals sell sadness | Sad or abandoned-cat stories are common; YouTube stopped paying for animal distress in July 2026. We stay monetizable with comedy |
| Deadline | From Feb 1, 2027 joining YPP takes 8,000 watch hours or 20M Shorts views (double). Channels already in stay in |
| Only YouTube pays us | TikTok doesn't pay Paraguay; Instagram pays only through brand deals |
| Clip channel | ~24 views per Short; remake engine 0 of 71 overnight; paused (clipper D66–D67) |

## Unit economics (prices of 2026-10-29)
| | |
|---|---|
| Cost per Short (2–4 Omni shots at 720p, retakes and checks included) | **~$2–3** |
| YPP entry today | 1k subs + **10M Shorts views in 90 days**, or 1k subs + 4,000 watch hours in 12 months |
| 10M in 90 days means | ~3.3M Shorts views/month: a few breakout Shorts, or ~45k average over ~220 Shorts |
| Shorts RPM | ~$0.03–0.33 per 1k views; Shorts revenue also needs ≥10M views per rolling 90 days from Feb 1, 2027 |
| Long-form RPM | ~$5–15 general audience; $1–3 if flagged made for kids |

## Plan and gates
| Phase | When | What | Cost | Gate |
|---|---|---|---|---|
| **0. Pilot** | Oct 30–Nov 1 | Character refs; 3 episodes by hand; Lucas judges the look | in the $30 | Look is right: no stutter, consistent characters, right colours |
| **1. Test** | 14 days | 1 Short/day | $30 + $20 | Day 10: stop if best <5k views and median <200. Day 14: keep if any Short ≥100k or median ≥3k |
| **2. Sprint** | weeks 3–12 | 2–3 Shorts/day + a weekly 10-min compilation (watch hours) | ~$180–270/month, Lucas's call at day 14 | Day 45: continue only at ≥3M Shorts views in the last 30 days |
| **3. Apply** | mid-January 2027 | Apply to YPP (10M/90 d or 4,000 h route) | — | Accepted before Feb 1, 2027 |
| **4. Expand** | 2027 | Shorts Series, brand deals, merch, TikTok/IG on a hit | — | ≥$1,100 net/month for 2 months |

**Honest odds:** most AI cat channels never take off; a few make $10k+/month. $30–50 tells us which side we're on.

## Hard rules
- Original characters only. No real people, no babies or kids, no lookalikes of existing characters, no real brands or logos, no outside music.
- General audience: adult work-life topics, cinematic look (not a toddler cartoon), `selfDeclaredMadeForKids=false`.
- No animal distress, rescue, injury, gore, sexual or cheating tropes, shock, politics.
- Every Short is a new story with a real joke (Meowffice's lesson); premise similarity < 0.85 vs the last 30; unique titles.
- ≤60 s. At most 3/day. Quality over quantity: a weak day posts nothing.
- YPP-ready from day 1: keep each Short's script, prompts, refs, rejected takes and edit log (what YouTube asks for in appeals).
- Budget: hard stop in code + prepaid Gemini credit. Never a second Google or Anthropic account. Keys only in `/opt/clipper/.env` (shared, S8).
- One channel. No backups.

## Budget for the 2-week test
| Item | Cost |
|---|---|
| 14 Shorts at Omni 720p, retakes included | ~$38 |
| Pilot look drafts at 360p + key test | ~$4 |
| Character refs (Nano Banana 2 Lite) | ~$1 |
| Radar: Gemini watches ~40 popping Shorts/day | ~$4 |
| Writing and checks | ~$1–2 |
| **Total (hard cap $50)** | **~$48–49** |

Paid as prepaid Gemini credit: **$30 at setup, +$20 only if the day-10 check passes.** ~G. 315k in total with Paraguay's 10% IVA (G. 5,740/USD). Claude's share comes from the existing Anthropic balance.
