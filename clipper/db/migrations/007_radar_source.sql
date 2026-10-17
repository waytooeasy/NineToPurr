-- 007: radar_candidates.source (issue #19, D29): 'twitch' (clips, default) | 'youtube' (live VOD moments).
-- For youtube rows: clip_id = 'yt:<video_id>:<start_s>', url = VOD url, video_id = YouTube id,
-- vod_offset = moment start (s, VOD-absolute), duration_s = moment length (<=60).

ALTER TABLE radar_candidates ADD COLUMN source TEXT NOT NULL DEFAULT 'twitch';
