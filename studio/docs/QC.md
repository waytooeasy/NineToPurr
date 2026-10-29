# Quality control (design)

Lucas's bar (Oct 28–29): no stuttery edits, no bad frames, colours right, nothing cheap-looking. QC runs before he ever sees a Short. Every glitch he catches becomes a new automatic check (regression list at the bottom), same rule as the clipper's D47.

**Two independent checkers (S7):** Claude Haiku 5.5 reads dense still frames (2 per second) for picture problems, reusing the clipper's D47 visual check; Gemini 3.8 Flash watches the moving video with sound for what stills can't show (stutter, morphs, flicker, audio, timing). A Short passes only when both pass. About a cent per Short each.

## 1. Shot checks (after each Omni shot)
Claude Haiku gets the shot's frames with the character refs and the prompt (picture checks); Gemini watches the shot itself (motion checks). Both answer in JSON.

| Check | Pass |
|---|---|
| Character match (each character vs its ref: species, colours, outfit, proportions) | score ≥ 0.8 each |
| Anatomy and artifacts: extra or missing limbs, melting faces or paws, warped objects | none |
| Text inside the picture (signs, screens, labels) | none or unreadable blur only; never garbled words |
| Real brands, logos, real people, kids | none |
| The beat happened (the action in the prompt is on screen) | yes |
| Camera jump, flicker or morph inside the shot | none |
| Look matches the bible's style line (not a toddler cartoon) | yes |

Fail → retake that shot (max 2; each retake costs its seconds and shows in the ledger) → still failing → `needs_human`.

## 2. Final checks (after assembly)
**Rules (ffmpeg, no AI):**
| Check | Pass |
|---|---|
| Size and rate | 1080×1920, constant fps, H.264 + AAC |
| Length | within the format's range, ≤ 60 s |
| Black or frozen frames | none longer than 0.3 s (blackdetect, freezedetect) |
| Stutter at cuts | no repeated or dropped frames at shot joins (frame-hash compare) |
| Loudness | −14 LUFS ± 2, true peak ≤ −1 dBTP, no silence > 1.5 s unless the script asks |
| Captions | inside the 9:16 safe zone, never over a face, spell-checked, match the script |

**Gemini watches the whole Short (with sound):**
| Check | Pass |
|---|---|
| Story | a one-line summary matches the premise; the payoff lands in the last 2–3 s |
| Continuity | same characters, colours and outfits across shots |
| Hook | something happens or is promised in the first 1.5 s |
| Policy | no real people, kids, brands, distress, gore, sexual content, outside music |
| Made-for-kids look | not kid-coded |

**Library checks:**
- Perceptual hash vs our own past Shorts: no near-duplicates.
- Premise similarity vs the last 30 premises < 0.85 (checked at the premise step too).
- Title and description unique on the channel.
- Episode spend ≤ `EPISODE_MAX_USD`.

Fail → automatic fix when one exists (re-render captions, retake one shot), else `needs_human` with the reason in Telegram.

## 3. Lucas's gate
Telegram shows the Short, its title, format, cost and any QC notes: ✅ Post · ❌ Kill · 🔁 Retake shot N. Kill and retake ask for a one-word reason (button list + free text).

## Regression list (grows with every caught glitch)
| # | Date | Glitch Lucas caught | New check |
|---|---|---|---|
| — | — | (empty until the pilot) | — |
