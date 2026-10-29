# What Lucas sets up (after go)

~50 minutes. Keys and tokens go straight into `/opt/studio/.env` or token files on the VM, **never in chat**, never in git. Steps 1–2 first; the rest can happen while HQ makes the pilot.

| # | What | How | Time |
|---|---|---|---|
| 1 | **Decide** | Say go; pick the cast (A/B/C, [`CAST-OPTIONS.md`](../series/CAST-OPTIONS.md)) and the voice default (wordless or narrator) | 2 min |
| 2 | **Peakz on hold** | YouTube Studio → Peakz Recaps → Content → select the remakes → Visibility: **Private**. HQ stops the clipper timers the same day (clipper D66) | 5 min |
| 3 | **Google Cloud project `prm-studio`** | console.cloud.google.com → new project → enable **YouTube Data API v3**, **YouTube Analytics API**, **Generative Language API** → link billing → Budgets & alerts: **$50**, alerts at 50/90/100% | 10 min |
| 4 | **Gemini + YouTube API keys** | aistudio.google.com → API keys → create a key **in `prm-studio`** → `/opt/studio/.env` as `GEMINI_API_KEY`. Then Cloud console → Credentials → API key restricted to YouTube Data API v3 → `YOUTUBE_API_KEY` (the radar's own search quota) | 5 min |
| 5 | **New YouTube channel** | youtube.com → Settings → Add or manage your channels → Create a channel (brand account on the same Google account). Name: HQ proposes 3 after the cast pick | 5 min |
| 6 | **Upload + analytics tokens** | OAuth client (Desktop app) in `prm-studio`, consent screen **published**, then the same `upload.py --auth` flow as the clipper (`clipper/docs/READINESS.md` steps 1–3), signed in as the **new channel** → `/opt/studio/youtube_token.json`; repeat read-only for `/opt/studio/analytics_token.json` | 10 min |
| 7 | **Telegram bot** | @BotFather → `/newbot` (e.g. `PRM_Studio_BOT`) → token + your chat id into `/opt/studio/.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_ID`) | 3 min |
| 8 | **Anthropic key + spend limit** (limit still open) | console.anthropic.com → API keys → a new key named `studio` on **your same account** (never a second account) → `ANTHROPIC_API_KEY` in `/opt/studio/.env`; Limits → keep a monthly cap. Studio writing adds ~$1–2 | 3 min |
| 9 | **AdSense + W-8BEN** (still open) | Needed before any payout; one AdSense covers both channels | 10 min |
| 10 | Optional: **repo private** | GitHub → waytooeasy/prm → Settings → Change visibility. Today anyone can read this plan. Private repos get 2,000 free Actions minutes/month (CI, Trend Scout, agents use some) | 1 min |

HQ's side the same day: write `/opt/studio/.env.example` (no values), create `/opt/studio` with the right permissions, confirm the Gemini key works with one 360p Omni test (~$0.30), stop the clipper timers.
