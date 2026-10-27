# remake — rebuild popping clipper Shorts from the streamer's own VOD (D58)

**Scope.** Takes a clipper Short that is popping right now (market scan, D48) and rebuilds it frame for frame
from the streamer's Twitch VOD: their seconds, cuts, crops/zooms/pans, wide-shot-over-blur, colour washes,
captions (text, colours, timing, position), look (grade + sharpening), aspect and fps, and their audio cut timing.
What we add: our title (their meaning, our words) and our handle. What we never add: their music (copyright) and
their pixels (D57: their Short is only measured, never reused or re-uploaded).

**Status.** Engine built and tested end to end on the study Short (SpecificMinds "Jason And Ron Goes On A Date",
DNiycSAWihg): 8 shots / 7 cuts found frame-exact, 99.7 % of frames mapped, wide shots and red flash rebuilt.
Runs from `clipper-remake.timer` (next run 5 min after the last ends, D63; one Short per run, ≤ `REMAKES_PER_DAY`). Its output enters
the normal flow as an `edited` clip: QC → visual check → Telegram ✅ Post.

## How it works
| Step | Module | What |
|---|---|---|
| pick | `run.candidates` | market.json Shorts: ≤ 60 s, ≤ 36 h old, ≥ 1500 views/h, Twitch streamer, not ours, not tried |
| download | `source.download_short` | yt-dlp; a YouTube bot check stops the run and retries later (never worked around, #64) |
| locate | `source.find` | VOD of the matched moment (D54 hint) or the streamer's archives; audio snippets + a dense audio pass find every part; only those VOD sections are downloaded (1080p60) |
| audio map | `amap.build` | every 0.2 s of the Short placed in the sections; offsets to the sample, gain per piece, exact switch points, bass hits and music bed reported |
| video map | `vmap.build` | SIFT + RANSAC per frame → exact crop; cuts where the mapping jumps; smooth camera path per shot; layout full / fit (+ fitted blur background, or their solid colour) |
| stacks | `panels` | stacked / overlay layouts (#130): sample frames probed for panels (pass 1's crop explains one region, SIFT on the rest finds the next), agreeing samples → template, seams refined on the pixels; then every frame mapped per panel → `stack` shots (rect + smoothed path per panel, fill colour). A panel missing or matching weakly at the shot's time is searched ±5 s in the stream (clippers re-sync the facecam reaction: iboclips showed it 2.3 s later) and gets its own `dt`; runs next to it try the same offset. Stack passes run in spawned workers (a fork after OpenCV threads can hang) |
| look | `look.build` | grade (cubic colour polynomial on low-passed aligned frames), sharpening amount, **per-frame colour transform** for their effects (green wash, red flash, black & white, fades; `overlay.mats`), caption-band energy |
| captions | `caps.build` | Haiku vision OCR at 10 fps → caption events, word reveal times; one position per Short; start/end refined on the pixels |
| base | `render.render(ass=None)` | the remake without captions (their colour effects included): `base.mp4` |
| caption look | `style.build` | measured on their frames vs `base` (D61): font by glyph shape (39 fonts in `style.FONTS`, fetched to `/opt/clipper/fonts`) + letter spacing, size by libass width, each word's real colour, position, outline, animation (pop / fade / none); shadow, glow, box from one Sonnet call → `style.json`. **Word colours are ours (D62):** `caps.our_colours`, multicolour, never theirs |
| best captions | `run.build_best` | burns caption candidates on `base` (measured look, the next 2 fonts, the study look) in our word colours, scores each with `match.score` (colour-blind on captions, D62), stops at captions ≥ 92 %, keeps the best |
| render | `render.render` | frames composed at their aspect (1080 wide) and fps, look + per-frame effects applied, stream audio crossfaded at their switch points, our own boom only on isolated bass hits (never a music bed) |
| match | `match.score` | per frame vs their Short: picture (outside the caption rows) and captions (our caption error vs their caption's own pixels); % of matching frames + the worst stretches. In the render sidecar json and in Telegram ("📐 match vs original") |
| title | `title.make` | Haiku: same hook, their names, never their wording |
| register | `run.register` | creators/sources/clips (`edited`, `caption_style='remake'`, `music_risk=0`, no `context_line`: it is the public description, so the clipper is never named there) + radar_candidates (`source='remake'`). Telegram shows the source Short from `remakes` |

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

## Keeping it running (2026-10-27)
- A run starts no new Short after 40 min (`REMAKE_RUN_BUDGET_S`); systemd's stop (`TimeoutStartSec=75min`) sends
  SIGTERM, which puts the Short back in the queue (not counted as an attempt) and cleans its media.
- Every run first sweeps media older than 2 h left by stopped runs (they filled the 38 GB disk by 2026-10-27), and the
  shared VOD audio cache `$CLIPPER_REMAKE/_vods` (24 h, 8 GB max): a whole VOD's audio is downloaded once and reused
  by the next Short from the same stream.
- yt-dlp gets a copy of `youtube_cookies.txt` (it rewrites the jar on exit; a full disk emptied the real file).

## Limits / next
- Layouts: full, fit and stack (#130: two or three crops of the same stream frame, bands or a box). Skipped
  (`layout not supported yet`) only when a region is not in the stream (their own cam, another source) or the
  surround is neither a blurred copy nor one colour. Stack panels are not re-aligned by `align.refine` yet (full only).
- Fonts: only the 39 free fonts in `style.FONTS`; a clipper's paid font (e.g. DIN, Gotham) gets the closest one by shape.
- Frames SIFT misses are filled by correlation around the predicted section frame with a neighbour's crop (#121).
- `frame_shift` moves whole output frames (cut, crop, section frame), never the section index: Twitch VODs are often
  30 fps stored at 60 fps (every other frame a duplicate), where one section frame is 0 or 2 of their frames (#121).
- Openings can still be mis-framed (AIJsi_csYws frames 0-14 map to a wrong crop): next for #121's follow-up.
- 1080-wide output; the study clipper uploads 2160x2880 (YouTube encodes 4K uploads better).
- A hook edit from Telegram (`needs_rerender`) does not apply to remakes yet.
- Needs YouTube to let the VM download the Short; while the bot check (#64) blocks, the timer just retries.
