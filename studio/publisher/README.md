# Publisher (design only)

**Status:** not built. Build order 6. Reuses the clipper's `upload.py` and bot pattern (moved to `shared/`) with the clipper's bot token and upload token (S8; the clipper is off) and Studio's own DB.

**Scope:** the Telegram bot (premise pick, ✅ Post / ❌ Kill / 🔁 Retake, `/status`, `/stats`, `/budget`, `/waves`, `/pause`, `/resume`, alerts, recap) and the YouTube upload.

| | |
|---|---|
| **In** | `premises`, `episodes` in `qc_passed`, the Studio channel's upload token |
| **Out** | `approvals`, `posts`; episodes `approved` → `published` |
| **Runs** | bot always on; upload check every 15 min; slot 15:00 Asunción |

**Upload metadata:** title, description, 3 hashtags, `categoryId` 23 (Comedy), `selfDeclaredMadeForKids=false`, `containsSyntheticMedia=true` only for photoreal shots, playlist per `episode` arc. Max 3/day ever; the test posts 1/day. The YouTube id is saved before the state flips (no double posts). Autonomy L0 during the test: nothing posts without ✅.
