# Editor

**Scope:** raw clip → finished Short. 9:16, facecam crop, hook text, word captions, zooms, title + tags. Copies trending formats.

**Status:** `clip.py` works (download → Whisper → 9:16 blurred bg → hook + 3-word captions → CSV log). Tested on synthetic video; download/transcribe untested on real VODs.

**Run:** `python clip.py <url>` then `python clip.py <url> --picks picks.json`

**Next:** format presets (facecam crop, zoom punches) driven by the Trend Scout format library.
