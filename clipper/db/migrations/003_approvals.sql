-- 003: clip state machine + Telegram approval gate (issue #6, D10)
-- Clip states: found -> captured -> drafted -> edited -> qc_passed -> approved -> published -> measured
-- Gate adds: killed, needs_rerender. Other modules own the earlier transitions.

ALTER TABLE clips ADD COLUMN state            TEXT NOT NULL DEFAULT 'found';
ALTER TABLE clips ADD COLUMN state_changed_at TEXT;
ALTER TABLE clips ADD COLUMN context_line     TEXT;   -- our angle, shown to Lucas and burned into the clip
ALTER TABLE clips ADD COLUMN hooks_json       TEXT;   -- JSON array of 3 hook strings from the Writer
ALTER TABLE clips ADD COLUMN approval_sent_at TEXT;   -- set once the bot has sent the clip to Lucas
ALTER TABLE clips ADD COLUMN last_error       TEXT;   -- latest error for this clip (any module)
-- chosen hook goes in the existing clips.hook_text

CREATE INDEX idx_clips_state ON clips(state);

-- Audit trail of every decision from the approval bot
CREATE TABLE approvals (
    id          INTEGER PRIMARY KEY,
    clip_id     INTEGER NOT NULL REFERENCES clips(id),
    decision    TEXT NOT NULL,                  -- approved | killed | needs_rerender
    hook_index  INTEGER,                        -- 1..3 when a Writer hook was chosen
    chosen_hook TEXT,                           -- approved hook text, or Lucas's edited hook
    decided_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_approvals_clip ON approvals(clip_id);
