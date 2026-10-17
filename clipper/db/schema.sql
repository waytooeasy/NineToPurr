-- Clipping engine: data model (SQLite)
-- Funnel: creators -> sources (streams/VODs) -> clips -> posts -> metrics -> payouts
-- Campaigns are tracked with snapshots so budget burn rate can be computed.

PRAGMA foreign_keys = ON;

-- Streamers / creators you clip
CREATE TABLE creators (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,         -- e.g. 'Kai Cenat'
    main_platform TEXT,                         -- twitch, kick, youtube
    channel_url   TEXT,
    language      TEXT DEFAULT 'en',
    notes         TEXT
);

-- Whop (or other marketplace) campaigns
CREATE TABLE campaigns (
    id                INTEGER PRIMARY KEY,
    marketplace       TEXT NOT NULL DEFAULT 'whop',
    external_id       TEXT UNIQUE,              -- campaign id on the marketplace
    creator_id        INTEGER REFERENCES creators(id),
    name              TEXT NOT NULL,
    cpm_usd           REAL NOT NULL,            -- pay per 1,000 verified views
    budget_total_usd  REAL,
    max_payout_per_post_usd REAL,               -- per-video cap, if any
    min_views_to_pay  INTEGER,                  -- view threshold, if any
    allowed_platforms TEXT,                     -- 'tiktok,youtube,instagram,x'
    allows_spanish    INTEGER,                  -- 1/0/NULL unknown
    rules             TEXT,
    status            TEXT DEFAULT 'watching',  -- watching | active | dropped | ended
    first_seen_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Periodic scrape of each campaign -> burn rate, competition
CREATE TABLE campaign_snapshots (
    id                    INTEGER PRIMARY KEY,
    campaign_id           INTEGER NOT NULL REFERENCES campaigns(id),
    taken_at              TEXT NOT NULL DEFAULT (datetime('now')),
    budget_remaining_usd  REAL,
    clipper_count         INTEGER,
    submission_count      INTEGER
);
CREATE INDEX idx_snap_campaign_time ON campaign_snapshots(campaign_id, taken_at);

-- Long-form source material (a stream VOD, a YouTube video)
CREATE TABLE sources (
    id            INTEGER PRIMARY KEY,
    creator_id    INTEGER NOT NULL REFERENCES creators(id),
    url           TEXT NOT NULL UNIQUE,
    title         TEXT,
    published_at  TEXT,
    duration_s    INTEGER,
    source_views  INTEGER,                      -- views of the original at fetch time
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Clips cut from sources (features here drive the virality model)
CREATE TABLE clips (
    id              INTEGER PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES sources(id),
    campaign_id     INTEGER REFERENCES campaigns(id),
    start_s         REAL NOT NULL,
    end_s           REAL NOT NULL,
    duration_s      REAL GENERATED ALWAYS AS (end_s - start_s) VIRTUAL,
    picked_by       TEXT NOT NULL DEFAULT 'ai', -- ai | human | ai+human
    model_score     REAL,                       -- Claude's predicted virality 0-1
    hook_text       TEXT,                       -- first on-screen line
    caption_lang    TEXT DEFAULT 'en',          -- en | es
    caption_style   TEXT,                       -- e.g. 'word-pop', 'subtitle'
    topic_tags      TEXT,                       -- 'reaction,prank,argument'
    minutes_after_source INTEGER,               -- speed: source publish -> clip ready
    file_path       TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_clips_source ON clips(source_id);
CREATE INDEX idx_clips_campaign ON clips(campaign_id);

-- Your posting accounts
CREATE TABLE accounts (
    id          INTEGER PRIMARY KEY,
    platform    TEXT NOT NULL,                  -- tiktok | youtube | instagram | facebook | x
    handle      TEXT NOT NULL,
    language    TEXT DEFAULT 'en',
    created_at  TEXT,
    status      TEXT DEFAULT 'active',          -- active | limited | banned
    UNIQUE(platform, handle)
);

-- One clip can be posted to several accounts/platforms
CREATE TABLE posts (
    id                  INTEGER PRIMARY KEY,
    clip_id             INTEGER NOT NULL REFERENCES clips(id),
    account_id          INTEGER NOT NULL REFERENCES accounts(id),
    platform_post_id    TEXT,
    url                 TEXT,
    posted_at           TEXT NOT NULL,
    caption             TEXT,
    hashtags            TEXT,
    submitted_to_campaign INTEGER DEFAULT 0,
    submission_status   TEXT,                   -- pending | approved | rejected
    UNIQUE(account_id, platform_post_id)
);
CREATE INDEX idx_posts_clip ON posts(clip_id);

-- Metric pulls over time (1h, 6h, 24h, 72h, 7d...)
CREATE TABLE post_metrics (
    id            INTEGER PRIMARY KEY,
    post_id       INTEGER NOT NULL REFERENCES posts(id),
    measured_at   TEXT NOT NULL DEFAULT (datetime('now')),
    hours_since_post REAL,
    views         INTEGER,
    likes         INTEGER,
    comments      INTEGER,
    shares        INTEGER,
    avg_watch_s   REAL
);
CREATE INDEX idx_metrics_post_time ON post_metrics(post_id, measured_at);

-- What actually got paid
CREATE TABLE payouts (
    id              INTEGER PRIMARY KEY,
    campaign_id     INTEGER NOT NULL REFERENCES campaigns(id),
    post_id         INTEGER REFERENCES posts(id),
    verified_views  INTEGER,
    gross_usd       REAL,
    fee_usd         REAL,                       -- marketplace fee (~7% reported on Whop)
    net_usd         REAL,
    net_pyg         REAL,                       -- what landed in the bank
    status          TEXT DEFAULT 'pending',     -- pending | paid | unpaid_budget_gone
    paid_at         TEXT
);
