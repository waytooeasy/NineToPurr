# PRM Studio — strategy (v1, 2026-10-29)

Owner: **PRM · 00 HQ**. Decisions: [`DECISIONS.md`](DECISIONS.md) · live state: [`STATUS.md`](STATUS.md) · evidence: [`MARKET.md`](MARKET.md). Mirrored in the Claude project doc `claude/11-studio-plan.md` (the repo wins).
**Status: design only. Nothing is built or bought until Lucas says go.**

## The model
- **One YouTube channel of original AI character Shorts:** a recurring cast of animals living adult human life (work, rent, commute, dating, groceries). Cast options: [`../series/CAST-OPTIONS.md`](../series/CAST-OPTIONS.md).
- **Ride the wave, own the cast:** every Short plays a format that is popping in AI Shorts *today* (the radar decides), with our characters and an original story. We copy formats, never content (S2).
- **Money:** YouTube ads. Shorts bring reach; long-form compilations bring watch hours and ~20–100× the RPM. English/US audience.
- **Lucas's role:** picks the day's premise in Telegram (auto-picks after 3 h) and taps ✅ on each Short during the test. About 5 minutes a day.

## Why this
| Fact | Number |
|---|---|
| Clip channel so far | 21 Shorts, ~512 views → ~24 views per Short. At 6/day that's ~4.3k views/month vs ~3.3M/month needed to hold the 10M/90 d Shorts floor: **~770× short** |
| Remake engine | 71 tries overnight Oct 28–29, 0 made; 52 failed on "footage not found". Original content has no footage to find |
| The live wave | AI animals in human life: one AI cat daily-life series ~450M views (China, Oct 26); same lane on IG/TikTok/YouTube in the West |
| Rules | July 2026: a recurring character or mascot is explicitly allowed; template clones and animal-distress bait are not |
| Recurring casts win | Fruit Love Island, Bandar Apna Dost (~2.07B views), FUNTASTIC YT (best month $9k) all run one cast across every video |

## Unit economics (prices of 2026-10-29)
| | |
|---|---|
| Cost per Short (3 shots × 8 s, Omni 720p, retakes and checks included) | **~$3** |
| Cheapest format (1 shot × 10 s) | ~$1 |
| Break-even views per Short on Shorts ads ($3 ÷ RPM) | 10k at $0.30 · **20k at $0.15** · 60k at $0.05 |
| Shorts pay floor from Feb 1, 2027 | 10M qualified views per rolling 90 d (~3.3M/month); below it Shorts earn $0 |
| Long-form YPP route | 1k subs + 4,000 watch hours in 12 months |
| Long-form RPM | ~$5–15 general audience; $1–3 if flagged made for kids |

**What that means:** Shorts alone pay only at millions of views a month. The money path is Shorts for reach → weekly long-form compilations of the best Shorts (no new generation cost) for watch hours, YPP and higher RPM. Scaling to 2/day costs ~$180/month, so it happens only after the numbers say so.

## Phases and gates
| Phase | What | Gate to the next |
|---|---|---|
| **0. Pilot** (2–3 days after go) | Lucas picks the cast. Character refs made. 3 episodes made by hand in a session (no pipeline yet). Lucas judges the look | Lucas says the look is right: no stutter, characters consistent, colours right |
| **1. Test** (14 days) | 1 Short/day, $50 hard cap ($30 + $20), Lucas ✅ each. Pipeline built in parallel by Build agents | Week-1 check (early stop), then the Day-14 call (below) |
| **2. Scale** (to ~day 60) | 2 Shorts/day, weekly long-form compilation, audience-vote arcs, auto-post with 🛑 Stop. Budget ~$180/month: Lucas approves it at the Day-14 call | Day-60 money check (below) |
| **3. Expand** (2027) | YPP, Shorts Series, a second format or cast only once the first holds | ≥$1,100 net/month for 2 months |

### Day-14 call (each Short measured at ≥48 h)
| Result | Call |
|---|---|
| Any Short ≥100k views, **or** median ≥3k views with ≥65% stayed (engaged/views) | **Keep** → Phase 2 |
| Median 500–3k, **or** best ≥20k | One more week (~$25), double down on the best format |
| Median <500 **and** best <20k | **Kill** this cast; next lane from the radar, or long-form |

Clip channel for comparison: median ~24.

### Day-60 money check
Continue only with **median ≥20k views per Short**, or **≥3.3M Shorts views/month**, or **≥1,000 long-form watch hours/month**. Otherwise stop the ad model for Studio.

## Hard rules
- Original characters only. No real people, no babies or kids, no lookalikes of existing characters, no real brands or logos, no copyrighted music.
- General audience, not made for kids: adult-life topics, cinematic look (not a toddler cartoon), `selfDeclaredMadeForKids=false`. Alert if YouTube flips a video to made for kids.
- No animal distress or rescue, no gore, no sexual or cheating tropes.
- Every Short is a new story: premise similarity check against the last 30, unique titles and descriptions, a human pick every day.
- ≤60 s per Short (test default 20–30 s). Never more than 3/day (spam policy); the test runs 1/day.
- Budget: a hard stop in code plus prepaid Gemini credit (Google refuses calls at $0). Never a second Google or Anthropic account. Keys only in `/opt/studio/.env`.
- One channel. No backup channels. Peakz remakes set to private before Studio's first upload (one termination bars every channel).

## Budget for the 2-week test
| Item | Cost |
|---|---|
| 14 Shorts at Omni 720p, retakes included (format mix in [`TEST-PLAN.md`](TEST-PLAN.md)) | ~$38 |
| Pilot look drafts at 360p + key test | ~$4 |
| Character refs (Nano Banana 2 Lite, ~30 images) | ~$1 |
| Radar: Gemini watches ~40 popping Shorts/day | ~$4 |
| Writing and checks (Claude, Gemini) + optional narrator TTS | ~$1–2 |
| **Total (hard cap $50)** | **~$48–49** |

**Upfront: $30** of prepaid Gemini credit at setup, **+$20 only if the week-1 check passes** (Shorts 1–7: stop early if the best has <5k views and the median <200). With Paraguay's 10% IVA on foreign digital services, ~G. 315k in total at G. 5,740/USD. Claude's ~$1–2 comes from the existing Anthropic balance. No subscriptions.

2 Shorts/day instead of 1: +~$38.

## Open questions for Lucas
1. **Cast:** A, B or C ([`CAST-OPTIONS.md`](../series/CAST-OPTIONS.md)). HQ pick: A.
2. **Voice:** wordless cast + SFX (HQ default; no voice drift, no language barrier) or a narrator voice.
3. **Peakz:** set the 21 remakes to private and pause the clipper at go (D66)?
4. **Repo:** it's public, so this plan is readable by anyone. Keep it public or make it private?
