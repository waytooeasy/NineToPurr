# remake — rebuild popping clipper Shorts from the streamer's own VOD (D58)

**Scope.** Takes a clipper Short that is popping right now (market scan, D48) and rebuilds it frame for frame
from the streamer's Twitch VOD: their seconds, cuts, crops/zooms/pans, wide-shot-over-blur, colour washes,
captions (text, colours, timing, position), look (grade + sharpening), aspect and fps, and their audio cut timing.
What we add: our title (their meaning, our words) and our handle. What we never add: their music (copyright) and
their pixels (D57: their Short is only measured, never reused or re-uploaded).

**Status.** Engine built and tested end to end on the study Short (SpecificMinds "Jason And Ron Goes On A Date",
DNiycSAWihg): 8 shots / 7 cuts found frame-exact, 99.7 % of frames mapped, wide shots and red flash rebuilt.
Runs from `clipper-remake.timer` (every 30 min, one Short per run, ≤ `REMAKES_PER_DAY`). Its output enters
the normal flow as an `edited` clip: QC → visual check → Telegram ✅ Post.

## How it works
| Step | Module | What |
|---|---|---|
| pick | `run.candidates` | market.json Shorts: ≤ 60 s, ≤ 36 h old, ≥ 1500 views/h, Twitch streamer, not ours, not tried |
| download | `source.download_short` | yt-dlp; a YouTube bot check stops the run and retries later (never worked around, #64) |
| locate | `source.find` | VOD of the matched moment (D54 hint) or the streamer's archives; audio snippets + a dense audio pass find every part; only those VOD sections are downloaded (1080p60) |
| audio map | `amap.build` | every 0.2 s of the Short placed in the sections; offsets to the sample, gain per piece, exact switch points, bass hits and music bed reported |
| video map | `vmap.build` | SIFT + RANSAC per frame → exact crop; cuts where the mapping jumps; smooth camera path per shot; layout full / fit (+ fitted blur background) |
| look | `look.build` | grade (cubic colour polynomial on low-passed aligned frames), sharpening amount, colour washes (flashes) per frame, caption-band energy |
| captions | `caps.build` | Haiku vision OCR at 10 fps → caption events, word reveal times, colours; one position per Short; start/end refined on the pixels; ASS in their style (Montserrat Black, glow + shadow, words fade/blur in) |
| render | `render.render` | frames composed at their aspect (1080 wide) and fps, look applied, libass captions, stream audio crossfaded at their switch points, our own boom on their bass hits |
| title | `title.make` | Haiku: same hook, their names, never their wording |
| register | `run.register` | creators/sources/clips (`edited`, `caption_style='remake'`, `music_risk=0`) + radar_candidates (`source='remake'`) |

Stages are cached as JSON in the work dir (`$CLIPPER_REMAKE/<short id>/`): a re-run after a fix redoes only what
was deleted. Media are deleted after each run (`--keep` keeps them).

## Run
```
cd /opt/clipper/repo/clipper
python -m remake.run --dry-run                 # what would be remade now
python -m remake.run                           # remake the most popping Short (what the timer runs)
python -m remake.run --short DNiycSAWihg --streamer "Stable Ronaldo" --published 2026-10-19T00:27:17Z --keep
pytest -q remake/tests                         # offline
```

## Limits / next
- Layouts: full and fit. A stacked layout (face cam on top of gameplay) is skipped (`layout not supported yet`).
- Font: always Montserrat Black (the study clipper's). Other clippers' fonts are next.
- Caption colours come from OCR (median per word); a pixel colour read is next.
- 1080-wide output; the study clipper uploads 2160x2880 (YouTube encodes 4K uploads better).
- A hook edit from Telegram (`needs_rerender`) does not apply to remakes yet.
- Needs YouTube to let the VM download the Short; while the bot check (#64) blocks, the timer just retries.
