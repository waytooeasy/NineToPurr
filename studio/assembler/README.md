# Assembler (design only)

**Status:** not built. Build order 4.

**Scope:** turn the shots into the finished Short.

| | |
|---|---|
| **In** | shot files, on-screen text cards, `formats/style.json`, `narrator.wav` (optional) |
| **Out** | `/opt/studio/out/<episode>.mp4` (1080×1920, H.264 + AAC) + `sidecar.json`; state `assembled` |
| **Engine** | ffmpeg; the clipper's caption renderer (moved to `shared/`) |
| **Cost** | $0 (VM CPU) |

**Rules:** hard cuts on the beat; a 2-frame audio crossfade at every join (no pops); constant fps, never a speed change; loudness −14 LUFS, true peak ≤ −1 dBTP; captions inside the safe zone; upscale 720→1080 with lanczos (the pilot compares it with Omni's own 1080p at +$0.05/s and keeps the better one). Phase 2 adds the weekly long-form compilation from the week's best Shorts.
