# Radar

**Scope:** find moments worth clipping and hand them to the Editor as `picks.json`.

**HQ decisions (D13, D14):**
- Twitch Get Clips first; live chat spikes later.
- Creators come from a config file (Kai first, multi-streamer).
- Rank by views per hour since creation; dedupe by VOD + overlapping timestamp (handle missing VOD offsets).
- Widen window to 7 days when the last 24 h is thin.
- Own table `radar_candidates` via `../db/migrations/002_radar.sql`.
- Radar does not write hooks; the Editor's Writer step does.

**Status:** not built.

**Needs:** Twitch app (dev.twitch.tv/console, 2FA, redirect `http://localhost`); Client ID + secret in `/opt/clipper/.env`.

**Next:** `twitch.py` → `top_clips.py` → `capture.py`, tests on sample responses, systemd timer handed to Infra.
