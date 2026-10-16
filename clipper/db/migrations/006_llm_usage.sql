-- 006: LLM token usage per call (issue #18, D31). Written by editor/llm.py so the Analyst can track cost.
-- kind: 'call' (normal) | 'batch' (Message Batches API, billed at 50%).
-- cache_creation_tokens / cache_read_tokens: prompt-cache writes / hits (Anthropic only).

CREATE TABLE llm_usage (
    id                    INTEGER PRIMARY KEY,
    ts                    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    provider              TEXT NOT NULL,
    model                 TEXT NOT NULL,
    kind                  TEXT NOT NULL DEFAULT 'call' CHECK (kind IN ('call','batch')),
    clip_id               INTEGER REFERENCES clips(id),
    batch_id              TEXT,
    input_tokens          INTEGER NOT NULL DEFAULT 0,
    output_tokens         INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_llm_usage_ts ON llm_usage(ts);
CREATE INDEX idx_llm_usage_clip ON llm_usage(clip_id);
