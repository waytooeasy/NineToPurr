# <Series name> — series bible

Copy this file to `series/<slug>/BIBLE.md` when Lucas picks a cast. The writers' room reads it on every run (prompt-cached), so keep it short and concrete. HQ owns it; the weekly learn step proposes edits, Lucas or HQ accepts them.

## 1. Logline
One sentence: who, where, what goes wrong every time.

## 2. World
- Places (max 5), each with one visual line the generator can reuse: *"open-plan office, grey carpet, monitors, window light from the left"*.
- Time of year follows the real calendar (Thanksgiving, payday, Monday).

## 3. Cast
| Name | Species | Look (fixed words used in every prompt) | Personality | Want | Flaw | Signature action |
|---|---|---|---|---|---|---|
| | | | | | | |

- **Refs:** `/opt/studio/series/<slug>/refs/<name>_main.png` (clean mid-shot portrait, neutral background) + optional `<name>_full.png`. Never in git.
- **Never changes:** colours, outfit, size relations between characters.

## 4. Look
- Style line used in every shot prompt: *"cinematic 3D animated film, soft realistic fur, natural lighting, muted palette, adult real-world setting"*.
- Banned looks: toddler cartoon, neon kids' colours, chibi proportions, text inside the generated image.

## 5. Sound
- Default: wordless. Characters sigh, gasp, mutter, laugh; real-world SFX; light original ambience. No dialogue, no music from outside.
- Narrator (only formats that need it): Gemini TTS voice `<voice name>`, fixed.
- On-screen text carries lines and thoughts (see 7).

## 6. Humor rules
- One situation, one turn, one payoff. The payoff lands in the last 2–3 seconds.
- Adult-life topics only (work, money, rent, dating, chores, commuting).
- Punch up at situations, never at real groups. No real people, brands, politics, religion.
- Banned: babies/kids, animal distress or rescue, gore, sexual or cheating tropes, bathroom humor as the main joke.

## 7. On-screen text
- Hook text in the first 1.5 s, ≤7 words, plain words, no emoji.
- Lines and thoughts as short captions, ≤5 words per card.
- Caption look follows today's `formats/style.json` (radar), inside the 9:16 safe zone.

## 8. Titles and metadata
- ≤60 characters, written like today's popping titles (`formats/library.md`), names the character or species, never misleading.
- Description: one line + 3 hashtags (series tag, species tag, #shorts).
- `selfDeclaredMadeForKids=false` always. `containsSyntheticMedia=true` only if a shot looks photoreal.

## 9. Continuity
| Ep | Date | Format | What changed in the world |
|---|---|---|---|
| | | | |

## 10. What works (filled by the weekly learn step)
- 
