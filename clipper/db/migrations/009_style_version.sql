-- 009: which caption style (editor/style.py version) a Short was rendered with.
-- The Telegram bot re-renders a qc_passed clip before sending it when today's market style differs
-- (Lucas, 2026-10-19: "always recheck the trending format before sending me the clips").
ALTER TABLE clips ADD COLUMN style_version TEXT;
