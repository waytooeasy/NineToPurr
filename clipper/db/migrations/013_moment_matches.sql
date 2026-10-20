-- 013: the streamer's own clip of a moment a top clipper's Short is popping with (D54, radar/match.py).
-- candidate_json = the Radar candidate (Twitch/Kick clip) to post; short_* = the clipper Short it matches.
CREATE TABLE IF NOT EXISTS moment_matches (
    short_id      TEXT PRIMARY KEY,
    streamer      TEXT NOT NULL,
    clip_id       TEXT NOT NULL,
    confidence    REAL,
    short_title   TEXT,
    short_vph     REAL,
    short_dur     REAL,
    candidate_json TEXT NOT NULL,
    matched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_moment_matches_clip ON moment_matches(clip_id);
-- one row per matching run; Radar matches once per market scan/refresh (radar/market.py)
CREATE TABLE IF NOT EXISTS match_runs (ran_at TEXT NOT NULL);
