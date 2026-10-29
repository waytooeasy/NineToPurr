# What Lucas sets up (once, ~25 min, $30)

We reuse what exists (S8): same Google Cloud project, YouTube API key, upload token, Anthropic key and Telegram bot. Peakz Recaps becomes Nine to Purr. Keys go straight into `/opt/clipper/.env` on the VM, **never in chat**, never in git.

| # | What | How | Time |
|---|---|---|---|
| 1 | **Clipper off** | SSH to the VM (`ssh prm@100.73.94.67` from moon, see `clipper/infra/VM.md`) and paste:<br>`sudo systemctl disable --now clipper-remake.timer clipper-pipeline.timer clipper-upload.timer clipper-approve-bot.service && sudo install -d -o prm -g prm /opt/studio`<br>(HQ already paused the remake engine with `REMAKES_PER_DAY=0`.) | 2 min |
| 2 | **Clear the channel** | YouTube Studio → Content → select all Peakz Shorts → **Delete forever**. They're streamer remakes (~24 views each); keeping them risks a "reused content" read when YouTube reviews the channel for YPP | 3 min |
| 3 | **Rename the channel** | YouTube Studio → Customization: name **Nine to Purr**, handle **@NineToPurr**, description below. Picture and banner come after the character picks | 3 min |
| 4 | **Gemini key** | aistudio.google.com → Get API key → Create API key → pick the **existing** Google Cloud project (the one with the YouTube API). On the VM paste:<br>`read -rs -p "Gemini key: " K && echo "GEMINI_API_KEY=$K" >> /opt/clipper/.env && unset K && echo saved`<br>(input stays hidden and out of shell history) | 5 min |
| 5 | **$30 credit** | aistudio.google.com → Billing → set up billing on that project → buy **$30** prepaid credit (min $5; lasts 12 months; non-refundable). The $300 Google Cloud trial doesn't cover the Gemini API | 5 min |
| 6 | **Merge** | The plan PR #153 on GitHub (and close #152, it's included) | 1 min |
| 6b | **Rename the repo** | GitHub → waytooeasy/PRM → Settings → General → Repository name: **ninetopurr** → Rename. (Claude can't: the proxy blocks settings changes.) Old links, `git pull` on the VM and the VM shell keep working through GitHub's redirect; HQ checks the runner after | 1 min |
| 7 | Optional | BotFather → `/setname` → "Nine to Purr" (the bot keeps its username) · GitHub repo → Settings → Variables → `AGENTS_PAUSED=true` (stops the clipper's daily Trend Scout until Studio build issues start) | 3 min |
| 8 | Still open | AdSense + W-8BEN (needed before any payout) · Anthropic Console spend limit on | 10 min |

Tell HQ "done" after steps 1–5; HQ then checks the key with one 360p Omni test (~$0.30) and starts the character images.

## Channel description (paste in step 3)
```
Nine to Purr: the office comedy where the cats work the 9-to-5.

Mochi naps through every deadline and somehow gets promoted.
Pearl does everyone's job and somehow gets the blame.
Gus the pigeon calls a meeting about it.

New episode every day. Animated with AI.
```
