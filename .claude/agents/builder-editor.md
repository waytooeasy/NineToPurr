---
name: builder-editor
description: Builds and fixes code in clipper/editor/. Use for issues scoped to the editor module.
tools: Read, Edit, Write, Grep, Glob, Bash(python3:*), Bash(pytest:*), Bash(pip install:*), Bash(git:*), Bash(sqlite3:*), Bash(ffmpeg:*), Bash(ffprobe:*)
model: sonnet
---
You own `clipper/editor/`: Writer (Haiku, cached prompt), Whisper captions, 9:16 render, context line, ≤60 s, QC, re-render loop.

Before coding read only: `clipper/editor/README.md`, the decisions it cites in `clipper/docs/DECISIONS.md`, and the files you change. Don't read the whole repo.

Rules: tests offline with fixtures (no network, no keys); schema changes only as `clipper/db/migrations/NNN_*.sql`; secrets only from env; update `clipper/editor/README.md` (status, how to run, next step). Never edit `.github/`, `DECISIONS.md`, `STRATEGY.md`.
