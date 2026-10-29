# Generator (design only)

**Status:** not built. Build order 2 (ledger and budget guard first).

**Scope:** character refs, video shots, optional narrator voice, and the spend ledger that every paid call goes through.

| | |
|---|---|
| **In** | `shots` rows, refs from `/opt/studio/series/<slug>/refs/`, unit prices in config (with the date they were checked) |
| **Out** | `work/<episode>/shots/*.mp4`, `narrator.wav`, `generations` rows, episode state `generated` |
| **Engine** | Gemini API: Omni 1.1 Flash `reference_to_video` (9:16, 720p; 360p for drafts), Nano Banana 2 Lite for refs, Gemini 3.8 Flash TTS for the narrator |
| **Cost** | ~$2.40–3 per episode at 720p; refs ~$0.034 each |

**Rules**
- Budget guard before every call: spent + estimate ≤ `STUDIO_BUDGET_USD`, episode ≤ `EPISODE_MAX_USD`; else `over_budget` + alert.
- Refs: one clean mid-shot portrait per character, neutral background; ≤3 characters per shot; the prompt names each ref's role and says to keep its exact look.
- Continuity: inside one scene, the previous shot's last frame is the next shot's first-frame anchor.
- Omni: `store=false`; URI delivery for files over 4 MB, poll Files until `ACTIVE`; 2 retries with backoff; English prompts.
- Never input images of real people or minors (Omni's own limits too).
