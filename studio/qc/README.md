# QC (design only)

**Status:** not built. Build order 5. The checks and thresholds are in [`../docs/QC.md`](../docs/QC.md).

| | |
|---|---|
| **In** | a shot (+ refs + prompt) or a finished Short (+ premise + script) |
| **Out** | `qc` JSON on the shot or episode; states `needs_retake`, `needs_human` or `qc_passed` |
| **Engine** | ffmpeg rules + Gemini 3.8 Flash watching the file (with sound) |
| **Cost** | ~$0.01–0.02 per Short |

**Rule:** every glitch Lucas catches gets a regression row in `docs/QC.md` and an automatic check, with a test.
