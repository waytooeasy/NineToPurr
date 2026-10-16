-- Radar: Twitch clip candidates, ranked by views per hour (DECISIONS D13, D14)
CREATE TABLE radar_candidates (
    id              INTEGER PRIMARY KEY,
    clip_id         TEXT NOT NULL UNIQUE,          -- Twitch clip id
    creator         TEXT NOT NULL,                 -- Twitch login
    broadcaster_id  TEXT,
    title           TEXT,
    url             TEXT NOT NULL,
    video_id        TEXT,                          -- source VOD id, NULL if VOD gone
    vod_offset      INTEGER,                       -- seconds into the VOD, NULL if unknown
    duration_s      REAL,
    view_count      INTEGER NOT NULL,
    clip_created_at TEXT NOT NULL,                 -- ISO 8601 UTC
    views_per_hour  REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'found', -- found -> captured -> ... (STRATEGY clip states)
    file_path       TEXT,                          -- set by capture.py
    found_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_radar_status_score ON radar_candidates(status, views_per_hour DESC);
CREATE INDEX idx_radar_vod ON radar_candidates(video_id, vod_offset);
