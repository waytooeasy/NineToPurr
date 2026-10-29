# Radar (design only)

**Status:** not built. Build order 3 ([`../docs/STATUS.md`](../docs/STATUS.md)), right after the ledger: the market drives every premise (S2). Until then HQ refreshes [`../docs/MARKET.md`](../docs/MARKET.md) by hand.

**Scope:** find the AI Shorts popping in our lane, have Gemini watch and tag them, cluster them into waves, write today's format files. This is how Studio "follows the market" (S2).

| | |
|---|---|
| **In** | YouTube Data API in the `prm-studio` project (`search.list` ≤ 80 of its 100 calls/day, `videos.list`, `channels.list`); RSS feeds of watched channels (free); Gemini 3.8 Flash watching public URLs (low media resolution, no downloads) |
| **Out** | `breakouts`, `waves`, `watch_channels` rows ([`../docs/DATA.md`](../docs/DATA.md)); `/opt/studio/formats/waves.json`, `library.md`, `style.json`; Telegram `/waves` |
| **Runs** | every 6 h (00/06/12/18 Asunción) |
| **Cost** | ~$0.25/day (≈40 Shorts watched) |

**How it scores**
- Searches: lane terms in `config/queries.yaml` (AI cat, AI animals funny, AI capybara, AI animation comedy, AI story, AI comedy ad, #aianimation, #aishorts …), last 72 h, short videos, English, US region, most viewed.
- **Breakout:** ≤72 h old, ≤3 min, English, and either ≥1,000 views/hour or ≥50k views at ≥20× the channel's subs with the channel under 100k subs. (Vuela's weekly bar is ≥200k views from channels under 30k; ours is lower to catch waves earlier.)
- **Watch:** the 10 newest breakouts per run → `tags` (format, cast type, length, shots, hook, beats, payoff, voice, caption look, kid-coded, policy flags, why it works).
- **Waves:** cluster by format + cast type; rising / peak / fading against the previous 72 h. Channels with ≥2 breakouts join `watch_channels`.

**Rules:** read and watch only; never download, reuse or re-upload their videos. Titles in `library.md` are patterns to paraphrase, never to copy.
