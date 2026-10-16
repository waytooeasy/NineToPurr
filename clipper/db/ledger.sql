-- ledger.sql — money layer for the clipping engine (run AFTER schema.sql)
-- No clients in this model, so P&L is per CHANNEL (and per campaign).
--   payouts  = earnings Whop credits per post (accrual: earned, maybe not landed)
--   ledger   = every real money movement in or out (cash: what actually moved)
-- All money stored in its original currency + converted to USD and PYG by trigger.

PRAGMA foreign_keys = ON;

-- ---------- structure additions to schema.sql ----------

-- Our own channels/brands (e.g. 'Main EN clips', 'ES clips', 'Recaps')
CREATE TABLE channels (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    language    TEXT DEFAULT 'en',
    niche       TEXT,                           -- e.g. 'US streamers'
    status      TEXT DEFAULT 'active',          -- active | paused | sold | dead
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

ALTER TABLE accounts  ADD COLUMN channel_id INTEGER REFERENCES channels(id);
ALTER TABLE campaigns ADD COLUMN kind TEXT DEFAULT 'clip';      -- clip | brand
ALTER TABLE payouts   ADD COLUMN earned_at TEXT;                -- when Whop credited it

-- Daily USD->PYG rate (one row per day you record it; nearest earlier date is used)
CREATE TABLE fx_rates (
    rate_date  TEXT PRIMARY KEY,                -- 'YYYY-MM-DD'
    usd_pyg    REAL NOT NULL
);

-- Recurring costs (VPS, Claude API plan, Upload-Post...). Posted into the ledger monthly.
CREATE TABLE subscriptions (
    id           INTEGER PRIMARY KEY,
    vendor       TEXT NOT NULL,
    category     TEXT NOT NULL,                 -- see ledger.category (out)
    amount       REAL NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'USD' CHECK (currency IN ('USD','PYG')),
    cadence      TEXT NOT NULL DEFAULT 'monthly' CHECK (cadence IN ('monthly','yearly')),
    channel_id   INTEGER REFERENCES channels(id),   -- NULL = shared by all channels
    isd_applies  INTEGER NOT NULL DEFAULT 1,        -- 10% ISD when paid with a PY card
    started_on   TEXT NOT NULL,
    ended_on     TEXT
);

-- ---------- the ledger ----------
CREATE TABLE ledger (
    id            INTEGER PRIMARY KEY,
    occurred_on   TEXT NOT NULL,                -- date the money moved
    direction     TEXT NOT NULL CHECK (direction IN ('in','out')),
    category      TEXT NOT NULL CHECK (category IN (
        -- in
        'whop_clip','whop_brand','youtube_ads','sponsor','affiliate','channel_sale','other_in',
        -- out
        'infra','ai_api','posting_tool','software','accounts','fees_fx','tax_isd','tax_irp','other_out')),
    counterparty  TEXT,                         -- Whop, Hetzner, Anthropic, Upload-Post...
    channel_id    INTEGER REFERENCES channels(id),  -- NULL = shared
    campaign_id   INTEGER REFERENCES campaigns(id),
    payout_id     INTEGER REFERENCES payouts(id),
    subscription_id INTEGER REFERENCES subscriptions(id),
    amount        REAL NOT NULL CHECK (amount >= 0),
    currency      TEXT NOT NULL DEFAULT 'USD' CHECK (currency IN ('USD','PYG')),
    fx_usd_pyg    REAL,                         -- filled by trigger
    amount_usd    REAL,                         -- filled by trigger
    amount_pyg    REAL,                         -- filled by trigger
    ref           TEXT,                         -- bank ref / invoice id
    note          TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_ledger_date ON ledger(occurred_on);
CREATE INDEX idx_ledger_channel ON ledger(channel_id);

-- Convert every entry to USD + PYG using the latest rate on/before its date
CREATE TRIGGER ledger_fx AFTER INSERT ON ledger
BEGIN
    UPDATE ledger SET
        fx_usd_pyg = (SELECT usd_pyg FROM fx_rates WHERE rate_date <= NEW.occurred_on
                      ORDER BY rate_date DESC LIMIT 1),
        amount_usd = CASE NEW.currency WHEN 'USD' THEN NEW.amount
                     ELSE NEW.amount / (SELECT usd_pyg FROM fx_rates WHERE rate_date <= NEW.occurred_on
                                        ORDER BY rate_date DESC LIMIT 1) END,
        amount_pyg = CASE NEW.currency WHEN 'PYG' THEN NEW.amount
                     ELSE NEW.amount * (SELECT usd_pyg FROM fx_rates WHERE rate_date <= NEW.occurred_on
                                        ORDER BY rate_date DESC LIMIT 1) END
    WHERE id = NEW.id;
END;

-- ---------- monthly routine: post this month's subscriptions (+10% ISD) ----------
-- Run once at the start of each month (the orchestrator can do it):
--   sqlite3 clip.db < post_subscriptions.sql   (the two INSERTs below)
-- INSERT INTO ledger (occurred_on, direction, category, counterparty, channel_id, subscription_id, amount, currency, note)
-- SELECT date('now','start of month'), 'out', category, vendor, channel_id, id, amount, currency, 'subscription'
-- FROM subscriptions s
-- WHERE started_on <= date('now') AND (ended_on IS NULL OR ended_on >= date('now','start of month'))
--   AND (cadence = 'monthly' OR strftime('%m', started_on) = strftime('%m','now'))
--   AND NOT EXISTS (SELECT 1 FROM ledger l WHERE l.subscription_id = s.id
--                   AND l.category <> 'tax_isd'
--                   AND strftime('%Y-%m', l.occurred_on) = strftime('%Y-%m','now'));
-- INSERT INTO ledger (occurred_on, direction, category, counterparty, channel_id, subscription_id, amount, currency, note)
-- SELECT date('now','start of month'), 'out', 'tax_isd', 'SET (ISD 10%)', channel_id, id, amount * 0.10, currency, 'ISD on ' || vendor
-- FROM subscriptions s
-- WHERE isd_applies = 1 AND started_on <= date('now') AND (ended_on IS NULL OR ended_on >= date('now','start of month'))
--   AND (cadence = 'monthly' OR strftime('%m', started_on) = strftime('%m','now'))
--   AND NOT EXISTS (SELECT 1 FROM ledger l WHERE l.subscription_id = s.id AND l.category = 'tax_isd'
--                   AND strftime('%Y-%m', l.occurred_on) = strftime('%Y-%m','now'));

-- ---------- views (the math) ----------

-- 1) Revenue by source, per month (cash that landed)
CREATE VIEW v_revenue_by_source AS
SELECT strftime('%Y-%m', occurred_on) AS month, category AS source,
       COUNT(*) AS entries,
       ROUND(SUM(amount_usd), 2) AS usd,
       ROUND(SUM(amount_pyg))    AS pyg
FROM ledger WHERE direction = 'in'
GROUP BY 1, 2;

-- 2) Costs by category, per month
CREATE VIEW v_costs_by_category AS
SELECT strftime('%Y-%m', occurred_on) AS month, category,
       ROUND(SUM(amount_usd), 2) AS usd,
       ROUND(SUM(amount_pyg))    AS pyg
FROM ledger WHERE direction = 'out'
GROUP BY 1, 2;

-- 3) Business P&L per month + running total (are we up or down overall?)
CREATE VIEW v_pnl_monthly AS
WITH m AS (
    SELECT strftime('%Y-%m', occurred_on) AS month,
           SUM(CASE WHEN direction='in'  THEN amount_usd ELSE 0 END) AS rev,
           SUM(CASE WHEN direction='out' THEN amount_usd ELSE 0 END) AS cost,
           SUM(CASE WHEN direction='in'  THEN amount_pyg ELSE -amount_pyg END) AS profit_pyg
    FROM ledger GROUP BY 1
)
SELECT month,
       ROUND(rev, 2)            AS revenue_usd,
       ROUND(cost, 2)           AS costs_usd,
       ROUND(rev - cost, 2)     AS profit_usd,
       ROUND(profit_pyg)        AS profit_pyg,
       ROUND(100.0 * (rev - cost) / NULLIF(rev, 0), 1) AS margin_pct,
       ROUND(SUM(rev - cost) OVER (ORDER BY month), 2) AS cumulative_profit_usd
FROM m ORDER BY month;

-- 4) Per-channel P&L: direct revenue/costs + shared costs split by share of views
CREATE VIEW v_channel_views_monthly AS
SELECT strftime('%Y-%m', p.posted_at) AS month, a.channel_id,
       COUNT(DISTINCT p.id) AS posts,
       SUM(lm.views)        AS views
FROM posts p
JOIN accounts a ON a.id = p.account_id
LEFT JOIN (SELECT post_id, MAX(views) AS views FROM post_metrics GROUP BY post_id) lm
       ON lm.post_id = p.id
WHERE a.channel_id IS NOT NULL
GROUP BY 1, 2;

CREATE VIEW v_channel_pnl AS
WITH direct AS (
    SELECT strftime('%Y-%m', occurred_on) AS month, channel_id,
           SUM(CASE WHEN direction='in'  THEN amount_usd ELSE 0 END) AS rev,
           SUM(CASE WHEN direction='out' THEN amount_usd ELSE 0 END) AS cost
    FROM ledger WHERE channel_id IS NOT NULL GROUP BY 1, 2
),
shared AS (
    SELECT strftime('%Y-%m', occurred_on) AS month,
           SUM(CASE WHEN direction='out' THEN amount_usd ELSE -amount_usd END) AS net_shared_cost
    FROM ledger WHERE channel_id IS NULL GROUP BY 1
),
tot AS (SELECT month, SUM(views) AS all_views FROM v_channel_views_monthly GROUP BY 1),
keys AS (SELECT month, channel_id FROM direct UNION SELECT month, channel_id FROM v_channel_views_monthly)
SELECT k.month, c.name AS channel,
       COALESCE(v.posts, 0)  AS posts,
       COALESCE(v.views, 0)  AS views,
       ROUND(COALESCE(d.rev, 0), 2)  AS revenue_usd,
       ROUND(COALESCE(d.cost, 0), 2) AS direct_costs_usd,
       ROUND(COALESCE(s.net_shared_cost, 0) * COALESCE(v.views, 0) / NULLIF(t.all_views, 0), 2) AS shared_costs_usd,
       ROUND(COALESCE(d.rev, 0) - COALESCE(d.cost, 0)
             - COALESCE(s.net_shared_cost, 0) * COALESCE(v.views, 0) / NULLIF(t.all_views, 0), 2) AS profit_usd,
       ROUND(1000.0 * COALESCE(d.rev, 0) / NULLIF(v.views, 0), 3) AS rev_per_1k_views,
       ROUND((COALESCE(d.cost, 0) + COALESCE(s.net_shared_cost, 0) * COALESCE(v.views, 0) / NULLIF(t.all_views, 0))
             / NULLIF(v.posts, 0), 3) AS cost_per_post
FROM keys k
JOIN channels c ON c.id = k.channel_id
LEFT JOIN direct d ON d.month = k.month AND d.channel_id = k.channel_id
LEFT JOIN v_channel_views_monthly v ON v.month = k.month AND v.channel_id = k.channel_id
LEFT JOIN shared s ON s.month = k.month
LEFT JOIN tot t ON t.month = k.month;

-- 5) Per-campaign P&L: which campaigns actually pay (effective CPM after fee + losses)
CREATE VIEW v_campaign_pnl AS
SELECT ca.name, ca.kind, ca.cpm_usd AS headline_cpm,
       COUNT(DISTINCT p.id) AS posts,
       SUM(CASE WHEN p.submission_status='approved' THEN 1 ELSE 0 END) AS approved,
       ROUND(100.0 * SUM(CASE WHEN p.submission_status='approved' THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN p.submitted_to_campaign=1 THEN 1 ELSE 0 END), 0), 1) AS approval_pct,
       SUM(py.verified_views)  AS verified_views,
       ROUND(SUM(CASE WHEN py.status IN ('pending','paid') THEN py.net_usd ELSE 0 END), 2) AS earned_net_usd,
       SUM(CASE WHEN py.status = 'unpaid_budget_gone' THEN py.verified_views ELSE 0 END) AS views_lost_to_budget,
       ROUND(1000.0 * SUM(CASE WHEN py.status IN ('pending','paid') THEN py.net_usd ELSE 0 END)
             / NULLIF(SUM(py.verified_views), 0), 3) AS effective_cpm_net
FROM campaigns ca
LEFT JOIN clips c  ON c.campaign_id = ca.id
LEFT JOIN posts p  ON p.clip_id = c.id
LEFT JOIN payouts py ON py.post_id = p.id
GROUP BY ca.id;

-- 6) Cash pipeline: earned on Whop but not in the bank yet (~10-day settle + withdrawal)
CREATE VIEW v_cash_pipeline AS
SELECT ca.name AS campaign, py.id AS payout_id, py.earned_at,
       date(py.earned_at, '+10 days') AS settles_about,
       date(py.earned_at, '+15 days') AS in_bank_about,
       py.net_usd
FROM payouts py
JOIN campaigns ca ON ca.id = py.campaign_id
WHERE py.status = 'pending'
ORDER BY settles_about;

-- 7) Foreign income year-to-date by source (hand this to the contador for RUC/IRP)
CREATE VIEW v_income_ytd AS
SELECT strftime('%Y', occurred_on) AS year, category AS source, counterparty,
       ROUND(SUM(amount_usd), 2) AS usd, ROUND(SUM(amount_pyg)) AS pyg
FROM ledger WHERE direction = 'in'
GROUP BY 1, 2, 3;
