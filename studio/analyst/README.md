# Analyst (design only)

**Status:** not built. Build order 8. Reuses the clipper's `metrics.py` (moved to `shared/`).

| Job | When | What |
|---|---|---|
| Stats | hourly for 48 h, then daily | views, likes, comments → `post_metrics` |
| Analytics | every 6 h | engaged views, stayed %, average % viewed, subs gained, shares → `post_analytics` |
| Made-for-kids watch | daily | what YouTube reports per video; alert on a flip |
| Recap | 23:00 Asunción | Telegram: views, stayed %, subs, spend vs cap, best and worst, top 3 waves |
| Learn | Sundays | Claude Sonnet compares formats and premises with results → findings to Telegram; accepted ones go to the bible (§10) and the room's weights |
| Day-14 / Day-60 report | on those days | the numbers for the calls in `docs/STRATEGY.md` |
