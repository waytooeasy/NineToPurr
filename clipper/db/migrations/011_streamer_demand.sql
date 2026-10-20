-- 011: Shorts demand per streamer (D48, radar/market.py): sum of views/hour of the top Shorts naming the
-- streamer in the last 48 h, any channel. NULL = no market data for that Heat run (old formula used).
ALTER TABLE streamer_heat ADD COLUMN demand REAL;
