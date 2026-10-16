# Automate the factory, transform every clip

In 2026, most people who say "AI agents run my Shorts channel" are running one orchestrator (Claude Code skills or subagents, n8n, or Hermes) on top of plain code: yt-dlp, faster-whisper, face-tracked ffmpeg and the YouTube Data API. An LLM makes about two calls per clip (which moment, which hook), and a human approves uploads. **No public source shows an agent-run streamer-clip channel with verified earnings.** Every claim of $10K–$25K a month comes from someone selling a tool or a course. The technology is cheap and already solved (about $0–15 a month on Lucas's VM), so YouTube's rules are the real constraint, not the code. The plan as written (raw streamer audio, no commentary, trending templates, many Shorts a day, many channels) matches YouTube's reused-content "not allowed" list almost point for point. It also matches the October 2026 Shorts reach cut for re-uploads and the spam policy's ban on "high volumes of similar content." From **February 1, 2027**, a channel earns $0 from Shorts in any month it is under **10M Shorts views per 90 days**, and new applicants will need **20M**. Netting $1,100 a month takes about **5–29M views a month**, depending on RPM. That is about 10× what the average Kai Cenat or IShowSpeed clip account gets. My recommendation is one multi-streamer channel that adds something of its own to every clip, Shorts of 60 seconds or less, and 3–5 posts a day. Plain code runs the pipeline, Gemini Flash-Lite writes the per-clip text, `claude -p` on the subscription handles 1–3 judgment jobs a day, and Lucas approves each upload on his phone through Telegram. "Thinking big" here means more views and more revenue per view on one channel, not more channels.

## Real agent teams are pipelines with two LLM decisions

The most transparent public case is Wei-ciao Wu. He runs two Claude agents: "Midnight" handles production, analytics and strategy, and "Dusk" handles promotion. The result was **52 videos in six weeks, 30,170 views, 29 subscribers and no revenue**, and Wu still approved ideas and reviewed every video before it went out ([dev.to](https://dev.to/wcamon/i-let-ai-agents-run-my-youtube-channel-for-6-weeks-heres-what-actually-happened-21b1)). The most literal "team" is collij22's set of eight Claude Code subagents, one per stage (research, script, assets, voice, assembly, upload, optimization, revenue), connected to n8n and MCP. It reports no channel results at all ([GitHub](https://github.com/collij22/yt-faceless-automation)).

The clip-focused repos all arrive at the same design:
- **skill-autoshorts** runs a daily cron skill: local Whisper, then Gemini picks clip boundaries and hooks, then ffmpeg, then approval by phone, then upload. A weekly `learn` step ranks clips by 0.6×views-z + 0.4×engagement-z and rewrites a `HOT.md` prompt file that feeds future runs ([GitHub](https://github.com/mutonby/skill-autoshorts)).
- **claude-shorts** scores 8–12 candidates on a weighted rubric: hook 0.30, coherence 0.25, emotion 0.20, value density 0.15, payoff 0.10 ([GitHub](https://github.com/AgriciDaniel/claude-shorts)).
- **Clips Kitty** combines the transcript, audio loudness, scene cuts, Twitch chat replay and YouTube "most replayed" data before an LLM re-ranks the finalists ([GitHub](https://github.com/ColinGPT9/clips-studio)).

The big-money claims fall apart when checked. Kellan Henneberry's "$24,937/mo" Shorts video shows no proof and promotes a tool ([YouTube](https://www.youtube.com/watch?v=V_t51u1tBJc)). "Printing $10K/Month on Autopilot" appears on the blog of Postiz, which sells the publishing layer ([Postiz](https://postiz.com/blog/ai-video-clipping-agent-postiz-stack)). A fact-check rated a "$39K faceless channel" claim "Half-true": it assumed a $0.33 RPM when the typical figure is $0.03–0.07 ([Income Reality Check](https://income-reality-check.pages.dev/a/how-a-faceless-channel-made-39k-with-claude-chatgpt/)). The one reported test of fully automatic clipping went badly: **about 300 AI-made clips in three weeks, and the best got 2,500 views** ([Forbes](https://www.forbes.com/sites/boazsobrado/2026/04/26/the-creator-of-clipping-who-powers-stakes-viral-machine/)).

Anthropic's own engineering guidance points the same way. It recommends predefined workflows first (prompt chaining, routing, parallelization, evaluator-optimizer) and fully autonomous agents only where the steps can't be predicted ([Anthropic](https://www.anthropic.com/engineering/building-effective-agents)). Multi-agent systems use **about 15× the tokens of a normal chat** and handle real-time coordination poorly. State should live in external storage, and agents should pass lightweight references to it rather than the content itself ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)). For a clip factory, that means a database state machine driven by code, with an LLM brought in at a few judgment points.

### The whole stack costs $0–40 a month, and SaaS tools hit their caps first

The research team estimated four ways to build the stack, using published unit prices:

| Stack | ~10 Shorts/day | ~50/day | Verdict |
|---|---|---|---|
| **A. Self-hosted:** Twitch Helix + yt-dlp, faster-whisper, MediaPipe reframe, ffmpeg captions, Python/systemd, Gemini 3.1 Flash-Lite, YouTube API direct, `claude -p` daily | ~$0–3 | ~$12 | This is Lucas's design. CPU time is the bottleneck. |
| **A+ Cross-post** via Upload-Post Basic | ~$19–27 | ~$28–36 | Only worth it once campaign income exists |
| **B. Cloud hybrid** (n8n Cloud Pro, Gemini Flash, Upload-Post Pro) | ~$100–110 | ~$130–165 | Only if the VM proves unreliable |
| **C. SaaS-heavy** (OpusClip/Vizard API + Submagic API) | ~$150–250 | Capped | Hits plan caps before 50/day |

The inputs behind those numbers:
- n8n Community Edition is free and has no execution cap ([Jet Admin](https://www.jetadmin.io/blog/n8n-pricing/)).
- Gemini 3.1 Flash-Lite costs $0.25 per 1M input tokens and $1.50 per 1M output tokens. On the paid tier, Google does not train on your data ([Google](https://ai.google.dev/gemini-api/docs/pricing)).
- A YouTube upload dropped from about 1,600 to about 100 quota units in December 2025. Since June 2026, `videos.insert` has its own quota bucket of **100 calls a day** ([YouTube API revision history](https://developers.google.com/youtube/v3/revision_history)).
- Upload-Post Basic costs $24 a month, or $16 billed annually ([Upload-Post](https://www.upload-post.com/pricing-comparison)).
- OpusClip's API caps its Pro and Max plans at 15 hours of video a month ([OpusClip](https://help.opus.pro/api-reference/overview)).
- Submagic's API plan allows about 100 videos ([CostBench](https://costbench.com/software/ai-video-editing-saas/submagic/)).

**Using Claude without the API.** The documented route is the official `claude` command-line tool run non-interactively (`claude -p`). It authenticates with a one-year `CLAUDE_CODE_OAUTH_TOKEN` created by `claude setup-token`, which the docs describe as meant "for CI pipelines, scripts" ([Claude Code auth](https://code.claude.com/docs/en/authentication)). Three traps:
- `--bare` mode ignores subscription credentials.
- If `ANTHROPIC_API_KEY` is set anywhere, `-p` always uses it instead of the subscription ([Claude Code auth](https://code.claude.com/docs/en/authentication)).
- Anthropic's legal page forbids routing subscription credentials through third-party apps, and says Pro/Max limits "assume ordinary, individual usage" ([Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)).

Pro allows roughly **10–40 Claude Code prompts per 5 hours**, shared with normal chat, though that figure may be out of date ([Claude support](https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan)). Cloud routines also run on the subscription, but:
- they run at most once an hour;
- they start from a fresh repo clone with no access to local files;
- a green status only means the session didn't crash, not that the task worked ([Routines](https://code.claude.com/docs/en/routines)).

In practice, Claude handles a few batched decisions a day on the VM, not one call per clip. n8n's AI Agent node needs its own model key, which Gemini can supply. n8n's most useful feature here is its human-review step for agent actions, which can send approvals through Telegram ([n8n docs](https://docs.n8n.io/build/integrate-ai/ai-examples/human-in-the-loop-for-tools)).

## The top clip channels post one or two hits a day, not fifty

CreatorDB counted every clip tagged with six big streamers over 30 days ending Aug 26, 2026. It found **3,266 Kai Cenat clips from 759 accounts, drawing 558M YouTube views**, and 4,835 IShowSpeed clips from 1,087 accounts, drawing 1.08B ([CreatorDB](https://creatordb.app/creator-news/the-rise-of-the-clip-economy/)). Views are concentrated at the very top. Eight channels took about 36% of all 1.68B clip views spread across 1,820 accounts, and none of them posted more than about 2.2 counted clips a day:

| Channel | Clips (30d) | Views (30d) | Views per clip |
|---|---|---|---|
| Nexxo Recaps | 23 | 111.2M | ~4.8M |
| deagzzzshorts | 8 | 91.8M | ~11.5M |
| Stream Bellz | 48 | 74.9M | ~1.6M |
| DaPlug | 53 | 71.6M | ~1.35M |
| Stream Vortex | 32 | 69.7M | ~2.2M |

Source: [CreatorDB](https://creatordb.app/creator-news/the-rise-of-the-clip-economy/). Most of the leaders are "Recaps" channels or feeds that cover several streamers, not fan pages for a single streamer.

**Sourcing comes down to speed.** There are three ways to find moments:
- Cut live while the stream runs: clips post within minutes.
- Pull community clips that viewers have already made.
- Have AI scan the VOD after the stream ends: about an hour behind ([ClipSpeed](https://www.clipspeed.ai/blog/clipping-twitch-streamers-youtube-shorts.html)).

Twitch's free API supports the first two:
- **Get Clips** returns a streamer's clips for a time window, sorted by views. In effect, it is free crowd-sourced moment detection.
- **Create Clip** captures 5–60 seconds from a live stream, using a user token with the `clips:edit` permission ([Twitch](https://dev.twitch.tv/docs/api/clips/)).

A chat-spike detector is simple code. Count chat messages in 10-second windows, flag windows running several times above the baseline, and start the clip about 30 seconds before the spike, because chat reacts after the moment ([OpusClip](https://www.opus.pro/mcp/inspiration/clip-the-moments-your-live-chat-exploded)). The most-viewed IShowSpeed content is edited live, during the stream, by a human ([Forbes](https://www.forbes.com/sites/boazsobrado/2026/04/26/the-creator-of-clipping-who-powers-stakes-viral-machine/)).

**There is one hard rule on format.** Any Short **over 60 seconds with an active copyright claim of any type is blocked worldwide and can't be monetized**. Shorts of 60 seconds or less aren't affected by this rule ([YouTube Help](https://support.google.com/youtube/answer/15424877?hl=en)). Beyond that, the guidance is vendor convention: 20–45 seconds, a cut from the setup line to the reaction, a face-tracked or split facecam layout, word-by-word captions, and titles under 70 characters that name the streamer ([ClipSpeed](https://www.clipspeed.ai/blog/clipping-twitch-streamers-youtube-shorts.html)). No public dataset ranks these formats by retention ([Bytecap](https://www.bytecap.io/research/youtube-shorts-retention-benchmarks)).

**Money per view is low.** Shorts RPM for US viewers is about $0.33, about $0.17 for gaming, and $0.07–0.20 for most niches ([AIR Media-Tech](https://air.io/en/air-data-findings/youtube-shorts-rpm-vs-long-form-how-much-do-shorts-earn-in-2026)). A fact-checker uses $0.03–0.07 as the 2026 average ([Income Reality Check](https://income-reality-check.pages.dev/a/how-a-faceless-channel-made-39k-with-claude-chatgpt/)).

Paid clipping campaigns pay more per view and don't require YouTube Partner Program (YPP) approval: $0.50–1.50 per 1K views on Whop, and $3 per 1K on Vyro ([CreatorDB](https://creatordb.app/creator-news/the-rise-of-the-clip-economy/)). But Whop's lifetime payouts average **only about $305 per earner** ([Business of Brand](https://artofthebrand.substack.com/p/how-clipping-became-a-billion-dollar)). One Kick-focused clipping program requires a 40%+ US audience and rejects 19 of every 20 applicants ([FindClout](https://findclout.com/blog/kick-clipping-program)). TikTok's Creator Rewards program is not open to Paraguay residents ([ShortSync](https://www.shortsync.app/resources/tiktok-creator-rewards-program-2026)), and it excludes reposted content anyway ([Business of Brand](https://artofthebrand.substack.com/p/how-clipping-became-a-billion-dollar)). So posting the same clips to other platforms adds reach, not income.

## YouTube's 2025–2027 rules are aimed squarely at raw clip farms

**Reused content.** YouTube's official "not allowed" list includes:
- "Clips from a show or other source edited together with little or no narrative"
- "Content uploaded many times by other creators"
- "Promotion of others' content, even with permission"

What is allowed is "Edited footage that adds a storyline and commentary," along with reactions that actually comment on the original ([YouTube Help](https://support.google.com/youtube/answer/1311392)). Reviewers judge the whole channel. They look at its main theme and at its most-viewed and newest videos. Permission from the streamer does not exempt a channel. The same page's inauthentic-content rule bans "AI-generated content built on generic templates without the creator's original insight."

**Spam.** The spam policy now names "using automated tools or AI to churn out high volumes of similar content with minimal changes." It also names **"detection evasion": speeding up audio, heavy filters, or cropping designed to get around abuse detection.** Penalties include strikes, and three strikes in 90 days can end the channel ([YouTube Help](https://support.google.com/youtube/answer/2801973)). The usual clip-farm tricks for looking "unique" are now spam violations, not just a monetization problem. In the enforcement wave of early 2026, YouTube deleted or hid videos from at least 18 AI-slop channels, including one with more than 1.2B views ([Tubefilter](https://tubefilter.com/2026/01/29/youtube-ai-slop-channel-crackdown-bans/)).

**October 2026 reach cut.** On Oct 2, 2026, YouTube said Shorts recommendations will "reduce the reach of content re-uploaded from other creators ... without adding anything of your own" ([9to5Google](https://9to5google.com/2026/10/02/youtube-wont-recommend-unoriginal-shorts/)). Rene Ritchie, YouTube's liaison to creators, said that none of these makes another creator's clip original: voice-over that just describes what's on screen, minor technical edits, or **template-based bulk changes** ([PPC Land](https://ppc.land/re-uploaded-shorts-lose-reach-as-youtube-favours-original-clips/)). Streamer news trackers summed it up: "Fan clip channels that repost raw stream moments are the ones affected" ([Upstream](https://upstream.so/blog/streamer-news-september-25-october-2-2026/)). YouTube has not published a threshold for how much change counts as "significant."

**February 2027 monetization floor.** From Feb 1, 2027, a channel gets Creator Pool money (Shorts ads plus Premium) only in months when it holds **10M qualified Shorts views over a rolling 90 days**. New channels applying through Shorts will need **20M views in 90 days plus 1,000 subscribers**, twice today's bar ([PPC Land](https://ppc.land/youtube-cuts-shorts-pay-for-channels-under-10m-views-from-february-2027/)). YouTube's YPP page confirms the Feb 1 update and says partners must accept the new terms by Jan 31, 2027 ([YouTube Help](https://support.google.com/youtube/answer/72851)). Views a Short gets before the channel accepts YouTube's Shorts monetization terms never pay ([YouTube Help](https://support.google.com/youtube/answer/12504220)).

**Rules for more than one channel.** One AdSense account per payee can monetize several channels, and YouTube refuses duplicate AdSense accounts ([YouTube Help](https://support.google.com/youtube/answer/9914702?hl=en)). A person whose channel is terminated may not use, own or create any other channel ([YouTube Help](https://support.google.com/youtube/answer/2802168)). Using sibling channels to get around a demonetization "could lead to termination of all channels" ([YouTube Help](https://support.google.com/youtube/answer/1311392)).

**Claims from the streamer's side.** In 2022, a rights company was copyright-striking IShowSpeed clip channels, apparently without Speed knowing ([Dexerto](https://www.dexerto.com/entertainment/ishowspeed-calls-out-company-for-false-copyrighting-fans-who-post-his-youtube-clips-1915952/)). The research found no evidence either way about Kai Cenat's team.

**Taxes.** The US has no income tax treaty with Paraguay ([IRS](https://www.irs.gov/businesses/international-businesses/united-states-income-tax-treaties-a-to-z)). Google therefore withholds **30% of earnings from US viewers** when tax info is on file. An individual who never files tax info loses **24% of all earnings** instead ([YouTube Help](https://support.google.com/youtube/answer/10391362)). Paraguay is eligible for YPP ([YouTube Help](https://support.google.com/youtube/answer/7101720)). Paraguayan domestic tax on this income (IRP) was not researched, so a contador's view is still needed.

### The $1,100 goal needs 5–29M views a month

This assumes 80% of revenue comes from US viewers, which means 24% total withholding. Netting $1,100 then takes about $1,450 gross, before Paraguayan tax and bank fees.

| RPM case | Basis | Views/month | Views/day | Avg views per Short at 5/day |
|---|---|---|---|---|
| $0.05 (low) | 2026 average $0.03–0.07 | ~29M | ~970K | ~193K |
| $0.15 (mid) | Most niches $0.07–0.20; gaming $0.17 | ~9.7M | ~320K | ~64K |
| $0.30 (US-heavy) | US viewers $0.33 | ~4.8M | ~160K | ~32K |

The mid case works out to about 30M views per 90 days. That is three times the 2027 floor, about a tenth of what a top-eight channel gets, and about **10× the average clip account** (around 923K views a month, per CreatorDB). The floor makes revenue all or nothing. At the mid RPM, a channel sitting exactly at the floor earns about $500 gross a month, and one just below it earns $0. Another way to read the numbers: Shorts brought in only 1.5% of revenue in the Entertainment category despite drawing about 26% of views ([AIR Media-Tech](https://air.io/en/air-data-findings/youtube-shorts-rpm-vs-long-form-how-much-do-shorts-earn-in-2026)).

## Nine places the plan collides with the evidence

| Plan item | What the evidence says | Change |
|---|---|---|
| Streamer audio only, no voiceover, copy trending formats | Matches the "little or no narrative" and "uploaded many times by other creators" items on the not-allowed list. Ritchie says template-based bulk changes don't count. | Keep streamer audio as the base. Add a **per-clip transformation layer** (see the next section). |
| Many Shorts a day | Top channels post 0.3–2.2 a day. Fully automatic AI clipping got 2,500 views at best. Spam policy bans high volumes of similar content. | **3–5 a day, curated.** QC enforces a hard cap. |
| Multiple channels from early on | The 10M floor applies per channel. Only one AdSense account. A termination bars every other channel. | **One channel** until it is above 20M per 90 days. Any later channel needs a distinct format. Never open a "backup" channel. |
| Kai Cenat first | 759 accounts clip Kai each month. The leaders cover several streamers or run recap formats. | **Multi-streamer brand name from day 1**, with Kai as the first source. |
| `clip.py --auto` calls the Anthropic SDK with `ANTHROPIC_API_KEY` | No API access, and a stray key overrides the subscription in `-p` mode. | Replace it with a provider-neutral `llm(prompt, schema)`: Gemini by default, `claude -p` for low-volume jobs. |
| STRATEGY.md: "~6 uploads/day, private until audit, manual phone upload" | Uploads now have their own 100-calls-a-day bucket. The `videos.insert` page reportedly no longer limits unverified projects to private uploads, but this is unconfirmed ([YouTube API](https://developers.google.com/youtube/v3/docs/videos/insert)). | Do **one test upload in week 1**. If it goes public, automate the publisher right away. |
| YPP gate of 1k subs + 10M per 90 days; RPM of $0.03–0.08 | The bar for new applicants doubles to 20M on Feb 1, 2027. RPM evidence spans $0.05–0.33. | Apply **before Feb 1** if on pace. Model all three RPM cases. |
| "A claimed Short's revenue goes to the claimant" | Not confirmed for claims on non-music content. What is confirmed: Shorts over 60 seconds with a claim are blocked. | Hard limit of **≤60 seconds**, a filter for music segments, and a per-streamer claims tracker. |
| YouTube payouts only, not Whop | Campaigns pay 3–10× the RPM without YPP, but the average Whop earner has made about $305 in total. Payouts to Paraguay are unverified. | Keep the campaign tables already in `schema.sql`. Add campaigns as a hedge in Phase 3 if payouts to Paraguay work. |

**The transformation layer.** YouTube rewards "storyline and commentary" and choices made clip by clip, not a shared template. The minimum version has three parts:
- **A context line** written for that specific clip: who, why it matters, what happened just before.
- **Captions that tell a story**, setting up the moment and then the payoff, rather than just transcribing the words.
- **Recap formats** that string 2–4 moments into one narrative, the format the top channels use.

Voice commentary in Lucas's own voice is the strongest signal of all, and it is worth an A/B test, recorded for only the 1–2 best Shorts each day. It has to be real opinion or context: Ritchie says voice-over that just describes what's on screen doesn't count. Synthetic AI narration over a template is exactly what the inauthentic-content rule describes, so it is not a fix. Gemini drafts the context and captions, and Lucas edits or approves them. That daily review is the "creator's original insight" YouTube's policy asks for, which makes his hour a day useful for compliance, not just quality control.

## Recommended architecture: code workers, three LLM roles, one human gate

The "agent team" is a database state machine. Each clip moves through these statuses: `found → captured → drafted → edited → qc_passed → approved → published → measured`. Plain-code workers are systemd services and timers on the VM. LLM roles sit only at judgment points. Every role reads and writes rows by ID, and no role passes content to another through conversation.

| Role | Type | Engine | Cadence | Writes |
|---|---|---|---|---|
| **Radar** | Code | Twitch Get Clips poll (top by views, last 2–24 h). Live chat-velocity detector (10-second windows, multiple of baseline, 30-second pre-roll). Audio loudness spikes. | Every 1–5 min while live | `moments` |
| **Capture** | Code | streamlink live buffer, yt-dlp, or the Twitch clip itself | On event | source file |
| **Writer** | LLM: Gemini 3.1 Flash-Lite (paid tier) | Transcript window in. Out: rubric score, 3 hooks, context line, title, as JSON | Per candidate | `clips.model_score`, hook variants |
| **Editor** | Code | faster-whisper word timings → ASS captions. MediaPipe face-tracked or split facecam (an upgrade on `clip.py`'s blur-fill). Format preset. ≤60 s | Per clip | mp4 |
| **QC gate** | Code + Lucas | Rules: ≤60 s, music flag, duplicate hash against own library, daily cap, spacing. Telegram approve / edit hook / kill. | Per clip | status |
| **Publisher** | Code | YouTube `videos.insert`, with the YouTube video ID saved per clip before marking it published, so a retry never posts twice | Fixed slots | `posts` |
| **Metrics + breaker** | Code | `videos.batchGetStats` hourly for the first 48 h. Analytics API daily for engagedViews and retention (data lags 48–72 h). Pause and alert when views drop below baseline, or on quota or claim events. | Hourly / daily | `post_metrics`, flags |
| **Analyst / Orchestrator** | `claude -p` (subscription) | Reads the daily export plus STRATEGY.md. Writes a JSON report and bounded proposals to change config. | 1×/day | `reports`, `config_proposals` |
| **Trend Scout** | `claude -p` or a cloud routine | Competitor channel RSS feeds plus view velocity → entries in the format library | Daily or weekly | `clipper/formats/*.md` in git |
| **Strategist** | Lucas + HQ chat | Weekly review | Weekly | STRATEGY.md |

The supporting data comes from these sources:
- `engagedViews` is the metric YouTube uses for monetization, while public view counts now start counting the moment playback begins ([YouTube Analytics revision history](https://developers.google.com/youtube/analytics/revision_history?hl=es-419)).
- `batchGetStats` costs 1 unit per call from its own 10,000-a-day bucket ([YouTube API revision history](https://developers.google.com/youtube/v3/revision_history)).
- Search is limited to 100 calls a day, so Trend Scout should follow competitor channels' RSS feeds, as Clips Kitty does ([GitHub](https://github.com/ColinGPT9/clips-studio)), rather than use search.

**Running Claude safely.** Use the unmodified `claude` tool, logged in to Lucas's own account. Store the `setup-token` in a root-only systemd `EnvironmentFile`. Never use `--bare`, and never set `ANTHROPIC_API_KEY`. Run with `--output-format json --json-schema`, `--permission-mode dontAsk`, a narrow `--allowedTools` list and `--max-budget-usd`, wrapped in `flock` and a `job_runs` row with an idempotency key ([headless docs](https://code.claude.com/docs/en/headless)). Don't feed the subscription into n8n or any proxy, and don't open a second account. Renew the token before it expires after one year. The Consumer Terms ban automated access "except ... where we otherwise explicitly permit it" ([Consumer Terms](https://www.anthropic.com/legal/consumer-terms)). The `setup-token` documentation is the explicit permission here, but no Anthropic document states a numeric limit for automation, so keep Claude jobs few and personal. Claude's biggest payoff is in the build chats, writing and maintaining this code, not in per-clip runtime work.

**Where n8n fits.** It is optional and should stay out of the path every clip travels. Its real value would be Telegram approval steps, routing alerts and manual triggers. It can expose workflows to `claude -p` through its MCP server ([n8n MCP](https://docs.n8n.io/connect/connect-to-n8n-mcp-server)). A small Python Telegram bot does the same job in Phases 0–1. Revisit n8n in Phase 2 only if Lucas wants a visual operations console.

**Autonomy is earned.** Each level unlocks only when the previous one has a track record:

| Level | Who decides an upload | Unlock condition (suggested) |
|---|---|---|
| L0 | Lucas approves every Short | Default for Phases 0–1 |
| L1 | Auto-publish above a score threshold; Lucas approves the rest | 2 weeks with ≥90% of Shorts approved unchanged and 0 blocked claims |
| L2 | Lucas spot-checks 1 in 5 after publishing | 30 days at L1 with no policy notices |
| L3 | Analyst can change config within ±10% a day | 60 days stable |
| Never | Creating channels, editing to evade detection, changing strategy | — |

**Thinking big means scale on more than one axis, in this order:**
1. **Hit rate and speed on one channel**: live detection, sharper angles.
2. **More streamers under the same brand.**
3. **More revenue per view.** Shorts earn 3–14% of long-form RPM, and long-form earns a median of about $2,300 per 1M views ([AIR Media-Tech](https://air.io/en/air-data-findings/youtube-shorts-rpm-vs-long-form-how-much-do-shorts-earn-in-2026)). A weekly long-form recap is therefore the biggest money lever, even though it breaks the "no long videos" rule.
4. **A second channel with a distinct format**, only once the first is safely above the floor.

The asset that scales is the engine, the format library and the performance data, not the number of channels.

## Roadmap, costs and risks

| Phase | Dates | Build / do | Gate to advance |
|---|---|---|---|
| **0. Compliant pilot** | Oct 17 – Nov 1, 2026 | Swap `clip.py` over to Gemini / `claude -p`. Transformation layer v1. ≤60-second hard limit plus a music flag. Telegram approval. One public test upload through the API. Multi-streamer channel brand. Tax form ready. 2–3 Kai Shorts a day. | ≥30 Shorts posted, ≥100K total views, 0 strikes or blocked claims |
| **1. Automate + YPP sprint** | Nov 2 – Dec 31 | Radar (Twitch Get Clips poll plus live chat detector), Capture, Editor with 3 formats A/B-tested (single moment / context / recap), QC, auto-publish after approval, hourly metrics. 3–5 a day. Add 1–2 streamers with mostly US audiences. | **YPP sprint: 10M views in the 90 days ending Jan 31 (about 111K a day) plus 1,000 subs → apply before Feb 1.** Checkpoint on Dec 31: ≥4M views since Nov 2, otherwise plan for the 20M bar. <1M by day 60 → change format or streamer. |
| **2. Learning loop** | Jan – Mar 2027 | `claude -p` Analyst and Trend Scout daily. Weekly `learn` step that rewrites a HOT.md prompt file. Config proposals. Circuit breaker. Autonomy L1–L2. Accept the new YPP terms by Jan 31. | YPP accepted, ≥10M views per 90 days sustained, ≥$500 net a month |
| **3. Scale revenue, then channels** | Apr 2027 onward | Push toward 20M+ views per 90 days. Test the campaign revenue line if Paraguay payouts work. Test a weekly long-form recap. Second distinct channel only after the main channel is ≥20M per 90 days and ≥$1,100 net for 2 months with 0 strikes. | Goal hit and holding |
| **Kill** | Any time | <3M views in the first 90 days → stop the ad model and switch to campaigns or another PRM project | — |

Under the 2018 duplication rules, a channel rejected for reused content could fix it and reapply after 30 days ([PPC Land](https://ppc.land/channels-removed-from-youtube-partner-program-due-to-duplication/)). That gives one retry inside the sprint window, which is why the transformation layer has to be in place before the first video goes viral.

**Monthly costs**

| Item | Phases 0–2 | Phase 3 | Note |
|---|---|---|---|
| Claude subscription | Existing | Existing | Upgrade to Max only if usage limits block the daily jobs |
| Gemini 3.1 Flash-Lite (paid) | ~$1–3 | ~$3–12 | Per-clip writer; paid tier means no training on the data |
| YouTube Data + Analytics APIs | $0 | $0 | Uploads have a 100-a-day bucket |
| Twitch API | $0 | $0 | Get Clips plus chat |
| n8n Community Edition (optional) | $0 | $0 | Self-hosted on the VM |
| Telegram bot | $0 | $0 | Approval gate |
| Upload-Post Basic | — | $16–24 | Only if campaigns need TikTok/IG/FB |
| **Cash total** | **~$1–3** | **~$3–36** | Fits the ~$24 budget. Electricity not counted. |

**Risk register**

| Risk | Likelihood | Impact | Mitigation | Warning sign |
|---|---|---|---|---|
| YPP rejected for reused content | High | No Shorts revenue | Transformation layer from day 1; recap and context formats; Lucas's edits | Rejection notice → fix, reapply in 30 days |
| October 2026 reach cut | High | Views capped | Same as above; speed; distinct angle per clip | Views per upload below the 14-day baseline |
| Spam strike (detection evasion, mass-produced similar clips) | Medium | Channel terminated | No mirroring, speed-up, pitch shift or filters; cap at 5 a day; no duplicate files | Any warning → pause uploads |
| Feb 2027 floor and 20M bar | High | $0 months | YPP sprint before Feb 1; put every view on one channel | 90-day views trending below 12M |
| Music Content ID claim | Medium | Short blocked if over 60 s | Hard limit of ≤60 s; music-segment flag | Claims per streamer |
| Rights company acting for the streamer | Unknown | Strikes | Per-streamer claims tracker; drop sources that draw claims; multi-streamer | First manual claim |
| Linked-channel cascade | Low now, High with more channels | Lose every channel | One channel; never open a backup | Before opening channel 2 |
| Anthropic subscription enforcement | Low–Medium | Lose Claude (needed for building) | Official tool, `setup-token`, 1–3 runs a day, no proxying, no second account | Errors or notices about the account |
| Kai Cenat saturation (759 accounts) | High | Low views | Live detection; multi-streamer; recaps | Median views per Short <5K after 30 Shorts |
| RPM below the model | Medium | Need 2–3× the views | Plan around the $0.05 case; long-form and campaign hedges | First AdSense month |
| Tax leakage | Certain | −24–30% | US tax form on file from day 1; contador for IRP | Before the first payout |
| Home VM downtime | Medium | Missed live moments | Auto-start; heartbeat table; Telegram alert | Missed heartbeat |
| 1 hour a day of Lucas's time | Medium | Approvals become the bottleneck | One-tap Telegram approvals; 5-a-day cap; autonomy ladder | Approval queue older than 2 h |

## Conclusion

The automation itself gives no edge: hundreds of clippers run the same yt-dlp → Whisper → ffmpeg stack, and fully automatic output did worst in the one reported test. The edge is in three things a solo builder can control: **getting to a moment fast** (live detection plus Twitch's own clip data), **a per-clip angle YouTube recognizes as original**, and **taste applied every day**. That reverses the original assumption. A human approval step is not a weakness in the automation. It is the "original insight" the inauthentic-content rule asks for. Claude is most valuable building and maintaining the engine and making one daily judgment call, not working inside the per-clip loop.

The February 2027 rule turns Shorts revenue into an on-off switch for each channel at 10M views per 90 days. That makes a channel farm the wrong shape of "big" for 2027: depth on one channel comes first, then more revenue per view (long-form recaps, campaigns), and breadth last. The biggest unknown is how much transformation is enough. YouTube publishes no threshold and no data on rejection rates for clip channels, so Lucas's own channel will produce the first real evidence. Instrument it from the first upload: format ID, hook variant, context type, claims and engaged views on every row.
