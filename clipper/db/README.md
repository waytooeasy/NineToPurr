# DB

**Scope:** SQLite schema, migrations and the migration runner. One file, `$CLIPPER_DB` (default `/opt/clipper/db/clip.db`), never in git.

**Decisions:** D14 (migrations dir), D22 (clip states), D24 (Writer output in the DB), D26 (`migrate.py`).

## Files
- `schema.sql`, `ledger.sql` — base (recorded as `001_base`). `math.sql` — reference queries.
- `migrations/NNN_name.sql` — everything after: `002_radar`, `003_approvals` (state machine + `approvals`), `004_clip_wiring` (`clips.title`, `clips.music_risk`, `radar_candidates.clips_id`), `005_qc` (`clips.file_hash`, `clips.qc_passed_at`), `008_streamer_heat` (`streamer_heat`: Heat Index snapshots, D33).
- `migrate.py` — applies base on a new DB, then each migration not in `schema_migrations(version, applied_at)`, in order, one transaction per file. Idempotent. A failure rolls that file back and stops.

## Run
```
python db/migrate.py                       # uses $CLIPPER_DB
python db/migrate.py --db /tmp/test.db
python db/migrate.py --baseline 002_radar  # VM DB where 002 was applied by hand: record it, don't re-run it
pytest db
```
`infra/setup.sh` calls it on every run (deploys too). Don't use raw `sqlite3 < file.sql` any more.

## Clip lifecycle wiring (who writes what)
| Step | Module | Writes |
|---|---|---|
| `found` | Radar `top_clips --picks N` | `clips` row (+ `creators`, `sources`), `radar_candidates.clips_id` |
| `captured` | Radar `capture.py` | `state`, `file_path` (the downloaded Twitch clip) |
| `drafted` | Editor `clip.py` after the Writer | `model_score`, `context_line`, `hooks_json`, `hook_text` (hook 1), `title`, `music_risk` |
| `edited` | Editor `clip.py` after render | `file_path` (the rendered Short) |

| `qc_passed` | Editor `qc.py` | `state`, `file_hash`, `qc_passed_at` |
| `qc_passed` again | Editor `rerender.py` (from `needs_rerender`) | `file_path`, `file_hash`, clears `approval_sent_at` |

Later states belong to the Telegram bot / Telegram bot / Publisher.

## Status / next
Built; `pytest db` covers fresh DB, upgrading a schema+ledger-only DB, rollback, and the found → edited walk with a mocked LLM.
Open: Radar creates `creators.name` = Twitch login (`kaicenat`), which may duplicate a hand-made `Kai Cenat` row. HQ call: add a display-name column or map in `creators.yaml`.
