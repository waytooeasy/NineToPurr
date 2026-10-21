---
name: shorts-format
description: How a PRM Short must look. Use when writing Writer prompts, render presets, captions or QC rules.
---
- **Follow the market (D36):** copy what works for the top clip channels *today*; don't invent rules. Today's facts live in `clipper/formats/library.md` (titles, hooks) and `clipper/formats/style.json` (caption style) on the `trends` branch, copied to `/opt/clipper/formats/` each pass.
- Sources: streamers' own footage (Twitch clips; Twitch/YouTube live VODs when reachable). Competitor Shorts are downloaded to study and imitate their edit (D57: parts of the stream used, cuts, zooms, captions, layout); their footage is never re-uploaded or reused. We post the streamer's own footage only.
- Copy the winning *format*, not the file: our own cut, our own captions, our own hook and title.
- **Length = the market's window (D37):** the clip/most-replayed window viewers chose; trim only dead air (≤2 s per end); no fixed minimum; hard cap 60 s. Open on the moment, not setup.
- **Look (D39, D40):** full-bleed 9:16 centred on the face, or facecam on top + gameplay below (`editor/layout.py`). No blurred bars, no banners. Captions per `style.json` (default: 2–3 words, heavy rounded sans, ALL CAPS, white + thick black outline, one keyword coloured, pop-in, mid-screen / on the seam). Hook ≤7 words, on screen 2.5 s. The context line is not on screen; it feeds the title/description.
- Title ≤70 chars, names the streamer, written like today's top Shorts (short, casual, 1–2 emoji, #streamer). No misleading claims.
- Never: speed-up, pitch shift, mirroring, heavy filters, crop tricks to dodge Content ID.
