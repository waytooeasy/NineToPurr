-- 012: YouTube Analytics per Short (owner-only data via the read-only analytics token, D53).
-- Lifetime totals through `through_date` (the API lags 1-2 days). stay = engaged_views / views
-- ("viewed vs swiped away" proxy since YouTube's 2025 Shorts view change); avg_view_pct = retention.
CREATE TABLE IF NOT EXISTS post_analytics (
    id             INTEGER PRIMARY KEY,
    post_id        INTEGER NOT NULL REFERENCES posts(id),
    measured_at    TEXT NOT NULL DEFAULT (datetime('now')),
    through_date   TEXT,
    views          INTEGER,
    engaged_views  INTEGER,
    avg_view_s     REAL,
    avg_view_pct   REAL,
    likes          INTEGER,
    subs_gained    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_post_analytics ON post_analytics(post_id, measured_at);
