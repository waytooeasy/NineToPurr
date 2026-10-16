-- 008: streamer_heat (issue #33, D33): Heat Index snapshots, one row per streamer per run (every 30 min).
-- D = views on clips created in the last 24 h, W = last 7 d, B = W/7 (daily baseline),
-- momentum = (D+1)/(B+1), live_now 0/1, saturation = competitor Shorts about the streamer in 24 h,
-- heat = ln(1+D)*(1+0.5*log2(momentum)) + 0.3*ln(1+B) + live bonus, opportunity = heat/(1+0.1*saturation).

CREATE TABLE streamer_heat (
    streamer    TEXT NOT NULL,
    ts          TEXT NOT NULL,                  -- ISO-8601 UTC
    D           REAL NOT NULL,
    W           REAL NOT NULL,
    B           REAL NOT NULL,
    momentum    REAL NOT NULL,
    live_now    INTEGER NOT NULL DEFAULT 0,
    saturation  REAL NOT NULL DEFAULT 0,
    heat        REAL NOT NULL,
    opportunity REAL NOT NULL,
    PRIMARY KEY (streamer, ts)
);
CREATE INDEX idx_streamer_heat_ts ON streamer_heat(ts);
