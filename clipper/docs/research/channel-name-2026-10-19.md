# Channel name research (2026-10-19)

**Method:** YouTube Data API on the VM. 10 channel searches ("<streamer> clips shorts", "streamer clips shorts", …) plus known competitors gave 154 channels. Pulled subs, views and video count, dropped the streamers' own channels, grouped by naming pattern. Then checked handle availability with `channels.list?forHandle=` for 48 candidates.

## What the market says
| Independent multi-streamer clip channel | Subs | Views | Videos | Views/video | Since |
|---|---|---|---|---|---|
| deagzzzshorts | 6.81M | 14.4B | 980 | 14.7M | 2022-10 |
| Goofy Recaps | 3.74M | 6.87B | 949 | 7.2M | 2024-05 |
| Nexxo Recaps | 907K | 1.63B | 135 | 12.1M | 2026-01 |
| Stream Bellz | 341K | 922M | 256 | 3.6M | 2023-05 |
| Streamer Clip Vault | 129K | 52M | 276 | 190K | 2023-01 |

- **All 4 winners use a coined, brandable word** (deagzzz, Goofy, Nexxo, Bellz), often with a stylized spelling (zzz, xx, z). Names run 12–13 characters. "Recaps" is in 2 of the top 4.
- **Descriptive names flop:** 43 "Twitch/Streamer Clips/Moments" channels have median 5 subs, and the best has 129K.
- **Streamer-name channels flop:** 114 "<Streamer> Clips/Shorts" channels have median 2 subs. They're capped at one streamer and carry impersonation risk. They also clash with our multi-streamer Heat Index.
- A name doesn't cause views, but every breakout channel has an ownable brand. No generic one broke out.

## Shortlist (handle free per API on 2026-10-19; confirm in YouTube's handle picker)
| Name | Handle | Why |
|---|---|---|
| **Peakz Recaps** (pick) | `@Peakz` | "peak" is streamer slang for the best moment ("that was peak"), which is exactly what we post. Stylized z like the market. 5-letter bare handle. Easy mark (P / summit / up-arrow). |
| Wildin Recaps | `@Wildin` | "wildin" = going crazy, which is the clip type. |
| Gassed Recaps | `@Gassed` | "gassed" = hyped. Slightly ambiguous outside US slang. |
| Dubz Recaps | `@DubzRecaps` | "dub" = W. `@Dubzz` is taken. |

Avoided: anything close to a competitor stem (Nexxo, Bellz, Goofy), streamer names, "Twitch"/"Kick", and taken handles (Rizzo 618K, Loudy, Juiced, Yappo, Clipzo, AuraRecaps…).
