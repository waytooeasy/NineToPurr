# 2-week test plan

Goal: find out in 14 Shorts whether an original AI cast in today's popping formats gets real views. Not money yet; that's the Day-60 check ([`STRATEGY.md`](STRATEGY.md)).

## Calendar (example: go on Fri Oct 30)
| Day | Date | Who | What |
|---|---|---|---|
| 0 | Oct 30 | Lucas | Says go, picks the cast (A/B/C) and the voice default, does [`SETUP.md`](SETUP.md) (~50 min) |
| 1 | Oct 31 | HQ | Writes the bible; ~10 Nano Banana ref candidates per character (~$1) → Lucas picks one each |
| 1–2 | Oct 31–Nov 1 | HQ | **Pilot:** 3 episodes made by hand on the VM (throwaway scripts, not merged). The look is iterated at 360p ($0.03/s); once Lucas says it's right, the 3 are rendered at 720p and become Shorts 1–3 |
| 2 | Nov 1 | Lucas | First Short goes up (manual upload with the Studio token) |
| 2–15 | Nov 1–14 | everyone | **1 Short/day at 15:00 Asunción.** Build agents ship the pipeline in parallel; each module replaces a manual step when it lands |
| 17 | Nov 16 | HQ + Lucas | Day-14 call, once the last Short is ≥48 h old |

## What we post
- 14 Shorts, 1/day, 20–30 s by default (the radar may move a format's length).
- At least 4 different formats from [`../formats/README.md`](../formats/README.md), so the test says which one wins. Planned mix: 4 `reversal`, 3 `day_in_life`, 2 `fake_ad`, 2 `pov`, 2 `episode` (one 2-part arc, ~30 s per part), 1 `meme_twist`; swapped toward whatever the radar shows rising that week. At 720p with ~15% retakes this mix costs ~$38.
- Every Short: our cast, an original story, English text on screen, no outside music.

## Lucas's daily routine (~5 min)
| Time | Tap |
|---|---|
| 08:00–11:00 | Pick 1 of 5 premises (or let #1 auto-pick at 11:00) |
| ~12:00 | ✅ Post / ❌ Kill / 🔁 Retake on the finished Short |
| 23:00 | Read the recap |

## Budget
| Item | Est. |
|---|---|
| 14 Shorts at 720p, retakes included (mix above) | ~$38 |
| Pilot look drafts at 360p + key test | ~$4 |
| Character refs (Nano Banana 2 Lite) | ~$1 |
| Radar (~40 Shorts watched/day from day 0) | ~$4 |
| Writing, checks, optional narrator | ~$1–2 |
| **Total** | **~$48–49; $50 hard stop in code** + Google Cloud budget alert at 50/90/100% |

Real cost per Short is measured from the ledger; if it runs above $3.50, the room shifts to cheaper formats (`pov`, `expect_reality`, `meme_twist`).

## What we measure (per Short, at 24 / 48 / 72 h)
| Metric | Source | Why |
|---|---|---|
| Views, engaged views, **stayed %** (engaged ÷ views) | Data API + Analytics (D53 method) | Hook strength |
| Average % viewed | Analytics | Payoff and pacing |
| Subs gained per 1k views | Analytics | Does the cast make people come back |
| Comments, shares | Data API / Analytics | Talkability; votes for `episode` arcs |
| Format, cast members, length, cost | our DB | What to repeat |
| Made for kids as YouTube reports it | Data API | General-audience check |

## Day-14 call
| Result | Call |
|---|---|
| Any Short ≥100k views, **or** median ≥3k with ≥65% stayed | **Keep** → Phase 2 (2/day, weekly long-form compilation, L1 autonomy; ~$180/month, Lucas's OK) |
| Median 500–3k, **or** best ≥20k | **One more week** (~$25): double the best format, drop the worst two |
| Median <500 **and** best <20k | **Kill this cast.** Next: the radar's top rising lane with a new cast, or long-form |

Clip channel for comparison: median ~24 views per Short.

## Risks during the test
| Risk | Watch | Answer |
|---|---|---|
| Omni can't hold our characters steady | Pilot; shot QC character score | Better refs (clean mid-shot portraits), shorter shots, first-frame anchors; worst case fewer characters per shot |
| New channel's first Shorts get tiny test audiences | Views in the first 24 h | Judge at 48–72 h, not the first hour |
| YouTube marks a Short made for kids | Daily status check | Change the look and topics; appeal by setting the audience in Studio |
| Lucas busy one day | Premise auto-picks at 11:00 | The Short waits for his ✅ from the phone; a missed day is a missed day, not a weaker Short |
| Spend runs ahead | Ledger, alerts at 50/80/100% | Hard stop at $50; cheaper formats |
