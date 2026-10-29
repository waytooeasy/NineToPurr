# Format library

**What a format is:** the shape of a Short (length, beats, shots, hook type, title pattern), never its content. The radar measures which formats are popping in AI Shorts; the writers' room only writes premises inside today's popping formats (S2).

## Files (generated on the VM, not in git)
| File | Written by | Read by | What |
|---|---|---|---|
| `/opt/studio/formats/waves.json` | radar, 4×/day | room, Telegram `/waves` | Popping clusters: format id, rising/peak/fading, Shorts in 7 d, median views/hour, median length, example video ids |
| `/opt/studio/formats/library.md` | radar, daily | room (prompt-cached) | Title patterns and hook lines of today's popping Shorts in our lane, paraphrase only |
| `/opt/studio/formats/style.json` | radar, daily | assembler | Caption look of today's popping AI Shorts in our lane: font family, case, colours, outline, words per card, position |

HQ copies a weekly snapshot of the waves into [`../docs/MARKET.md`](../docs/MARKET.md).

## Seed formats (2026-10-29)
| id | Shape | Length · shots | Cost tier | Evidence |
|---|---|---|---|---|
| `reversal` | One situation → it goes right → it goes wrong (or the reverse). Title teases the turn | 15–30 s · 2–3 | ~$2–3 | Slop TV's animal reversal: 1M views in 3 days |
| `day_in_life` | "A day as a …": commute → work → overtime → snack. Montage of 3–4 beats, last beat is the joke | 20–30 s · 3–4 | ~$3 | The cyber-furball cat office series (~450M, China) |
| `fake_ad` | Fictional product, deadpan demo, absurd result. Narrator voice allowed | 15–25 s · 2–3 | ~$2–3 | AI comedy ads: 43M, 36M, 36M views |
| `pov` | "POV: you're …" first-person camera on a character's reaction | 10–20 s · 1–2 | ~$1–2 | POV labels across this month's popping AI Shorts |
| `expect_reality` | Expectation shot vs reality shot | 10–20 s · 2 | ~$1–2 | Classic Shorts format; cheapest two-beat joke |
| `meme_twist` | Our cast plays a situation that's a meme this week, with our own twist. Never their video, their audio or their words | ≤15 s · 1–2 | ~$1 | "Me At Work" cat meme (Oct); weekly meme lists |
| `episode` | Arc part N: 3–5 beats, cliffhanger, "comment A or B" decides part N+1 | 30–60 s · 3–5 | ~$3–6 | Fruit Love Island's voting; 21% of tracked AI shorts are episodic, 11% end on a cliffhanger |

Rules for every format: hook text in the first 1.5 s; payoff in the last 2–3 s; ≤60 s; one new story per Short.
