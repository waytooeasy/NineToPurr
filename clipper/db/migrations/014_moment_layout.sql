-- 014: the layout the matched clipper Short uses (full / fit / stack), read from its thumbnail (radar/match.py):
-- the Editor copies it for that moment (Lucas 2026-10-21: "Did we do the same as him").
ALTER TABLE moment_matches ADD COLUMN layout TEXT;
