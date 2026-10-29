# Test plan: pilot, 14-day test, sprint

Goal: find out fast whether Nine to Purr gets real views, then sprint to the YouTube Partner Program before Feb 1, 2027 ([`STRATEGY.md`](STRATEGY.md)).

## Calendar
| Day | Date | Who | What |
|---|---|---|---|
| 0 | Oct 29–30 | Lucas | [`SETUP.md`](SETUP.md): clipper off, channel renamed, Gemini key + $30 (~25 min) |
| 1 | Oct 30–31 | HQ | Ref candidates per character (~$1) → Lucas picks in Telegram/chat; profile picture and banner from the picks |
| 1–2 | Oct 31–Nov 1 | HQ | **Pilot:** 3 episodes by hand on the VM. Look iterated at 360p ($0.03/s); once Lucas says it's right, rendered at 720p → Shorts 1–3 |
| 2–15 | Nov 1–14 | everyone | **1 Short/day at 15:00 Asunción.** Build agents ship the pipeline in parallel; each module replaces a manual step when it lands |
| 10 | Nov 10 | HQ + Lucas | **Day-10 check** (Shorts 1–7, each ≥48 h old): pass → Lucas tops up $20; fail → stop |
| 16 | Nov 16 | HQ + Lucas | **Day-14 call** (all 14 ≥48 h old) |
| 17–75 | Nov 17–Jan 14 | everyone | **Sprint** (if kept): 2–3 Shorts/day + weekly 10-min compilation |
| 45 | ~Dec 14 | HQ + Lucas | **Pace check:** ≥3M Shorts views in the last 30 days, else drop the YPP-before-Feb-1 goal |
| ~75 | mid-Jan | Lucas | Apply to YPP |

## What we post in the test
- 14 Shorts, 1/day, 20–40 s, from the pilot seeds and the radar's formats ([`../formats/README.md`](../formats/README.md)).
- At least 4 formats, so the test says which one wins: ~4 `reversal`, 3 `day_in_life`, 2 `pov`, 2 `expect_reality`, 2 `episode` (one 2-part arc), 1 `meme_twist`. `fake_ad` waits until a narrator voice is tested.
- Every Short: our cast, an original joke with a payoff, English text on screen, no outside music.

## Lucas's daily routine (~5 min)
| Time | Tap |
|---|---|
| 08:00–11:00 | Pick 1 of 5 premises (or #1 auto-picks at 11:00) |
| ~12:00 | ✅ Post / ❌ Kill / 🔁 Retake on the finished Short |
| 23:00 | Read the recap |

During the pilot, before the bot is rebuilt, HQ sends previews to Telegram and Lucas answers in chat.

## Money
| When | Pay | Covers |
|---|---|---|
| Setup | **$30** prepaid Gemini credit | Refs, key test, pilot drafts (~$5), Shorts 1–7 (~$19), radar and checks (~$3) |
| Day-10 check passes | **$20** | Shorts 8–14 (~$19), radar (~$1) |
| Day-14 keep | ~$180–270/month (Lucas decides) | Sprint: 2–3 Shorts/day |

Hard stop in code at the approved amount; prepaid credit at $0 makes Google refuse calls (second cap). If real cost per Short runs above $3.50, the room shifts to cheaper formats (`pov`, `expect_reality`, `meme_twist`).

## Keep / kill
| Check | Stop | Keep |
|---|---|---|
| Day 10 (Shorts 1–7) | best <5k views **and** median <200 | otherwise |
| Day 14 (Shorts 1–14) | median <500 **and** best <20k | any Short ≥100k, **or** median ≥3k with ≥65% stayed |
| Day 45 (sprint pace) | <1M Shorts views in the last 30 days | ≥3M (on pace for 10M/90 d) |

Between the two: one more week (~$25), double down on the best format.
Clip channel for comparison: median ~24 views per Short.

## What we measure (per Short, at 24 / 48 / 72 h)
| Metric | Source | Why |
|---|---|---|
| Views, engaged views, **stayed %** (engaged ÷ views) | Data API + Analytics (D53 method) | Hook strength |
| Average % viewed | Analytics | Payoff and pacing |
| Subs per 1k views | Analytics | Does the cast make people come back (YPP needs 1k subs) |
| Comments, shares | Data API / Analytics | Talkability |
| Format, cast, length, cost | our DB | What to repeat |
| Made for kids as YouTube reports it | Data API | General-audience check |

## Risks
| Risk | Watch | Answer |
|---|---|---|
| Omni can't hold the characters steady | Pilot; shot QC character score | Clean mid-shot refs, shorter shots, first-frame anchors, fewer characters per shot |
| New-channel test audiences are tiny | Views in the first 24 h | Judge at 48–72 h |
| YouTube marks a Short made for kids | Daily status check | Adjust look and topics; set the audience in Studio |
| YPP review rejects AI content | Review at application | Policy-safe show, human picks every day, appeal pack (scripts, prompts, refs, takes, edit logs) |
| Spend runs ahead | Ledger, alerts at 50/80/100% | Hard stop; cheaper formats |
