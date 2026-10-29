---
name: studio-format
description: How a PRM Studio Short must look and what it may contain. Use when writing room prompts, Omni shot prompts, caption presets, QC rules or upload metadata for studio/.
---
- **Follow the market for the format, never the content (S2).** Today's popping formats, title patterns and caption look come from `/opt/studio/formats/` (radar). Our cast, stories, jokes and look are always our own.
- **Cast:** only the characters in `studio/series/<slug>/BIBLE.md`, with their fixed look words and refs. No real people, babies or kids, lookalikes of existing characters, real brands or logos.
- **Shape:** hook in the first 1.5 s (≤7 words on screen, plain words, no emoji); one situation; payoff in the last 2–3 s; ≤60 s (test default 20–30 s); 9:16, 1080×1920.
- **Sound:** wordless cast by default (S5): sighs, gasps, laughs, real-world SFX, original ambience. Narrator (Gemini TTS, fixed voice) only for formats that need one. No outside music or trending sounds.
- **Look:** cinematic 3D film style, soft realistic fur, natural light, muted adult palette, real-world adult settings. Never a toddler cartoon (made-for-kids risk).
- **Topics:** adult life (work, money, rent, dating, chores, commuting). Never animal distress or rescue, gore, sexual or cheating tropes.
- **Edit:** hard cuts on the beat, 2-frame audio crossfades, constant fps, no speed changes, captions in the safe zone, −14 LUFS.
- **Metadata:** title ≤60 chars in today's pattern but our own words; 3 hashtags; `selfDeclaredMadeForKids=false`; `containsSyntheticMedia=true` only for photoreal shots.
- Checks and thresholds: `studio/docs/QC.md`. Rules map: `studio/docs/POLICY.md`.
