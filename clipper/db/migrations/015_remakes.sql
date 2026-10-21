-- D58: every Short is a remake of a popping clipper Short (remake/run.py). One row per clipper Short tried.
CREATE TABLE IF NOT EXISTS remakes (
    short_id    TEXT PRIMARY KEY,                 -- the clipper's YouTube Short id
    streamer    TEXT,                             -- watchlist name the market scan filed it under
    channel     TEXT,                             -- the clipper's channel
    title       TEXT,                             -- their title (ours goes to clips.title)
    views       INTEGER,
    vph         REAL,
    published   TEXT,                             -- ISO 8601 UTC
    status      TEXT NOT NULL DEFAULT 'picked',   -- picked | working | done | skipped | failed
    vod_id      TEXT,                             -- the streamer's Twitch VOD it was rebuilt from
    vod_s       REAL,                             -- VOD seconds it covers
    vod_e       REAL,
    clip_id     INTEGER REFERENCES clips(id),     -- our Short (state edited -> QC -> Telegram)
    last_error  TEXT,
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_remakes_status ON remakes(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_remakes_vod ON remakes(vod_id, vod_s);
