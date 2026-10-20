-- 010: visual check of the finished Short before it can post (Lucas 2026-10-20: "should not repeat mistakes").
-- JSON from editor/visual_qa.py: {"ok": true|false|null, "issues": [...], ...}. NULL = not checked yet.
ALTER TABLE clips ADD COLUMN visual_qa TEXT;

-- What the visual check learned about a streamer: own_captions = their stream burns in live captions,
-- so the Editor adds none of its own (Sykkuno, Valkyrae; 2026-10-20). creator = radar_candidates.creator.
CREATE TABLE IF NOT EXISTS creator_flags (
    creator       TEXT PRIMARY KEY,
    own_captions  INTEGER NOT NULL DEFAULT 0,
    noted_at      TEXT NOT NULL DEFAULT (datetime('now')),
    note          TEXT
);
