# PRM Studio

Original AI character Shorts: a recurring cast of animals living adult human life, playing whatever format is popping in AI Shorts today. Paid by YouTube ads (Shorts for reach, long-form compilations for watch hours).

**Status: design only (2026-10-29).** Nothing is built, bought or posted until Lucas says go ([`docs/STATUS.md`](docs/STATUS.md)).

## Read in this order
1. [`docs/STATUS.md`](docs/STATUS.md): what runs, what waits
2. [`docs/STRATEGY.md`](docs/STRATEGY.md): the plan, the math, the gates (HQ-owned)
3. [`docs/DECISIONS.md`](docs/DECISIONS.md): S-numbered decisions (HQ-owned)
4. [`docs/MARKET.md`](docs/MARKET.md): what's popping, with sources
5. [`docs/PIPELINE.md`](docs/PIPELINE.md): how a Short gets made
6. [`docs/QC.md`](docs/QC.md), [`docs/POLICY.md`](docs/POLICY.md), [`docs/DATA.md`](docs/DATA.md): contracts for builders
7. [`docs/TEST-PLAN.md`](docs/TEST-PLAN.md), [`docs/SETUP.md`](docs/SETUP.md): the 2-week test and Lucas's setup

## Layout
```
studio/
├── docs/        strategy, decisions, market, pipeline, data, QC, policy, test plan, setup
├── series/      one bible per cast (text); refs and video live on the VM
├── formats/     format library contract + seed formats (radar output lives on the VM)
├── radar/       popping AI Shorts → waves, formats, caption style
├── room/        premises, scripts, storyboards, titles
├── generator/   character refs, Omni shots, spend ledger, budget guard
├── assembler/   concat, on-screen text, sound, upscale
├── qc/          shot and final checks
├── publisher/   Telegram bot + YouTube upload
├── analyst/     stats, analytics, recap, weekly learn
├── db/          schema + migrations
└── infra/       systemd units, .env.example, health
```
Module folders hold a design README only until the build starts.

## Relation to the clipper
Same repo, same VM, same rules (CLAUDE.md). Separate channel, DB (`/opt/studio`), Google Cloud project, Telegram bot and budget (S3). The clipper is paused at go (clipper D66); its uploader, metrics, captions and health code get extracted into `shared/` for both.
