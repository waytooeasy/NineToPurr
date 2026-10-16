-- 005: QC v1 + re-render loop (issue #12, D27)
-- file_hash: sha256 of the rendered Short, set when QC passes it (duplicate check vs our library).
-- qc_passed_at: first time QC passed the clip; the daily cap of 5 counts these (UTC day).

ALTER TABLE clips ADD COLUMN file_hash    TEXT;
ALTER TABLE clips ADD COLUMN qc_passed_at TEXT;

CREATE INDEX idx_clips_file_hash ON clips(file_hash);
