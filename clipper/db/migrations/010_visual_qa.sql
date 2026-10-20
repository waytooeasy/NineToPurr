-- 010: visual check of the finished Short before it can post (Lucas 2026-10-20: "should not repeat mistakes").
-- JSON from editor/visual_qa.py: {"ok": true|false|null, "issues": [...], ...}. NULL = not checked yet.
ALTER TABLE clips ADD COLUMN visual_qa TEXT;
