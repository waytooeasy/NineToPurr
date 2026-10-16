-- 004: wire clip states across Radar/Editor (issue #11, D22-D24)
-- Writer output lands on clips (D24); radar_candidates points at its clips row.

ALTER TABLE clips ADD COLUMN title      TEXT;      -- Writer title (<=70 chars, names the streamer)
ALTER TABLE clips ADD COLUMN music_risk INTEGER;   -- 1/0 from the Writer; QC flags 1 in Telegram

ALTER TABLE radar_candidates ADD COLUMN clips_id INTEGER REFERENCES clips(id);
CREATE INDEX idx_radar_clips_id ON radar_candidates(clips_id);
