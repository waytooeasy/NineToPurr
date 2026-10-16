-- The math layer. Each query answers one decision.

-- 1) FUNNEL: X sources -> X clips -> X views -> $X  (per creator, last 30 days)
SELECT  cr.name                                   AS creator,
        COUNT(DISTINCT s.id)                      AS sources,
        COUNT(DISTINCT c.id)                      AS clips,
        ROUND(1.0 * COUNT(DISTINCT c.id) / NULLIF(COUNT(DISTINCT s.id),0), 1) AS clips_per_source,
        SUM(lm.views)                             AS total_views,
        ROUND(1.0 * SUM(lm.views) / NULLIF(COUNT(DISTINCT c.id),0))           AS views_per_clip,
        ROUND(SUM(p2.net_usd), 2)                 AS net_usd
FROM creators cr
JOIN sources s   ON s.creator_id = cr.id
JOIN clips c     ON c.source_id = s.id
LEFT JOIN posts p ON p.clip_id = c.id
LEFT JOIN (SELECT post_id, MAX(views) AS views FROM post_metrics GROUP BY post_id) lm
       ON lm.post_id = p.id
LEFT JOIN payouts p2 ON p2.post_id = p.id
WHERE c.created_at >= datetime('now','-30 days')
GROUP BY cr.id
ORDER BY net_usd DESC;

-- 2) CAMPAIGN PICKER: budget burn rate and days left
WITH ordered AS (
    SELECT campaign_id, taken_at, budget_remaining_usd, clipper_count,
           ROW_NUMBER() OVER (PARTITION BY campaign_id ORDER BY taken_at DESC) AS rn
    FROM campaign_snapshots
),
latest AS (SELECT * FROM ordered WHERE rn = 1),
day_ago AS (
    SELECT s.campaign_id, s.budget_remaining_usd
    FROM campaign_snapshots s
    JOIN latest l ON l.campaign_id = s.campaign_id
    WHERE s.taken_at <= datetime(l.taken_at, '-1 day')
    GROUP BY s.campaign_id
    HAVING s.taken_at = MAX(s.taken_at)
)
SELECT  ca.name, ca.cpm_usd,
        l.budget_remaining_usd,
        (d.budget_remaining_usd - l.budget_remaining_usd)                    AS burn_usd_per_day,
        ROUND(l.budget_remaining_usd /
              NULLIF(d.budget_remaining_usd - l.budget_remaining_usd, 0), 1) AS days_left,
        l.clipper_count,
        ROUND(l.budget_remaining_usd / NULLIF(l.clipper_count,0), 2)         AS budget_per_clipper
FROM campaigns ca
JOIN latest l   ON l.campaign_id = ca.id
LEFT JOIN day_ago d ON d.campaign_id = ca.id
WHERE ca.status IN ('watching','active')
ORDER BY days_left DESC, ca.cpm_usd DESC;
-- Rule of thumb: skip campaigns with days_left < 3 (clips verify too late to get paid).

-- 3) EXPECTED VALUE PER CLIP, by campaign
--    EV = avg verified views x CPM / 1000 x (1 - fee)
SELECT  ca.name,
        COUNT(DISTINCT p.clip_id)                              AS clips,
        ROUND(AVG(lm.views))                                   AS avg_views,
        ROUND(AVG(lm.views) * ca.cpm_usd / 1000 * 0.93, 3)     AS ev_usd_per_clip
FROM campaigns ca
JOIN clips c  ON c.campaign_id = ca.id
JOIN posts p  ON p.clip_id = c.id
JOIN (SELECT post_id, MAX(views) AS views FROM post_metrics GROUP BY post_id) lm
     ON lm.post_id = p.id
GROUP BY ca.id
ORDER BY ev_usd_per_clip DESC;

-- 4) WHAT HITS: views by feature (run one GROUP BY per feature)
--    Swap the grouped column: caption_lang, caption_style, picked_by,
--    duration bucket, post hour, minutes_after_source bucket.
SELECT  c.caption_lang,
        CASE WHEN c.duration_s < 20 THEN '<20s'
             WHEN c.duration_s < 40 THEN '20-40s'
             WHEN c.duration_s < 60 THEN '40-60s'
             ELSE '60s+' END                                   AS length_bucket,
        strftime('%H', p.posted_at)                            AS post_hour_utc,
        COUNT(*)                                               AS posts,
        ROUND(AVG(lm.views))                                   AS avg_views,
        SUM(CASE WHEN lm.views >= 10000 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS hit_rate_pct
FROM clips c
JOIN posts p ON p.clip_id = c.id
JOIN (SELECT post_id, MAX(views) AS views FROM post_metrics GROUP BY post_id) lm
     ON lm.post_id = p.id
GROUP BY 1, 2, 3
HAVING posts >= 5
ORDER BY avg_views DESC;

-- 5) SPEED: does clipping faster pay?
SELECT  CASE WHEN c.minutes_after_source <= 60  THEN '<=1h'
             WHEN c.minutes_after_source <= 360 THEN '1-6h'
             WHEN c.minutes_after_source <= 1440 THEN '6-24h'
             ELSE '>24h' END                                   AS speed,
        COUNT(*) AS posts, ROUND(AVG(lm.views)) AS avg_views
FROM clips c
JOIN posts p ON p.clip_id = c.id
JOIN (SELECT post_id, MAX(views) AS views FROM post_metrics GROUP BY post_id) lm
     ON lm.post_id = p.id
GROUP BY 1 ORDER BY avg_views DESC;

-- 6) EARLY SIGNAL: 1h views vs final views (decide fast what to repost / cut)
SELECT  p.id AS post_id,
        MAX(CASE WHEN m.hours_since_post <= 1.5 THEN m.views END) AS views_1h,
        MAX(m.views)                                              AS views_final,
        ROUND(1.0 * MAX(m.views) /
              NULLIF(MAX(CASE WHEN m.hours_since_post <= 1.5 THEN m.views END),0), 1) AS multiplier
FROM posts p JOIN post_metrics m ON m.post_id = p.id
GROUP BY p.id
HAVING views_1h IS NOT NULL;

-- 7) AI vs YOU: does human picking beat the model?
SELECT  c.picked_by, COUNT(*) AS posts, ROUND(AVG(lm.views)) AS avg_views,
        ROUND(AVG(c.model_score), 2) AS avg_model_score
FROM clips c
JOIN posts p ON p.clip_id = c.id
JOIN (SELECT post_id, MAX(views) AS views FROM post_metrics GROUP BY post_id) lm
     ON lm.post_id = p.id
GROUP BY c.picked_by;

-- 8) MONTHLY P&L + KILL CHECK
SELECT  strftime('%Y-%m', p.posted_at)        AS month,
        COUNT(DISTINCT p.id)                  AS posts,
        SUM(lm.views)                         AS views,
        ROUND(SUM(py.net_usd), 2)             AS net_usd,
        ROUND(SUM(py.net_pyg))                AS net_pyg,
        CASE WHEN SUM(lm.views) < 100000 OR COALESCE(SUM(py.net_usd),0) < 50
             THEN 'KILL' ELSE 'CONTINUE' END  AS verdict   -- 30-day kill criteria
FROM posts p
LEFT JOIN (SELECT post_id, MAX(views) AS views FROM post_metrics GROUP BY post_id) lm
       ON lm.post_id = p.id
LEFT JOIN payouts py ON py.post_id = p.id
GROUP BY 1 ORDER BY 1 DESC;
