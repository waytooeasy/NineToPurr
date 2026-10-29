# YouTube rules → our design

Checked 2026-10-29 ([`MARKET.md`](MARKET.md#policy-facts) has the sources). If a rule changes, update this table and the QC checks in the same PR.

| Rule | What it means for us | Where it's enforced |
|---|---|---|
| **Inauthentic content** (July 16, 2026): generic or template content that varies little is not monetized | Every Short is a new story inside a format; Lucas picks the premise; no find-and-replace scripts; unique titles | room (similarity < 0.85 vs last 30), QC library checks, Lucas's pick |
| A recurring character or mascot and a fixed episode structure **are allowed** | Our cast and our seed formats are fine as long as the substance changes | bible, room |
| Content made to upset or manipulate (YouTube's example: animal in distress, then rescued) is not monetized | No distress, rescue, injury or cruelty plots, even as a joke | bible humor rules, QC policy check |
| AI personas of real people on finance, legal or health: not monetized | No real people at all; no advice content | bible, QC |
| Spam: high volumes of similar content | Max 3/day ever; test 1/day; near-duplicate check | publisher cap, QC |
| Altered or synthetic disclosure | Clearly animated → no label needed; any photoreal shot → `containsSyntheticMedia=true` on upload | publisher, bible look |
| **Made for kids** (COPPA): animated characters are one factor; topic, audience, language and songs decide; animation for everyone is general audience | Adult-life topics, film look, no kids' songs or toys, `selfDeclaredMadeForKids=false`, daily check of what YouTube reports and an alert if it flips | bible, QC kid-coded check, analyst |
| Copyright | Original characters, no lookalikes of existing ones, no outside music or trending sounds, no real brands | room prompt rules, QC |
| Others' videos | The radar only reads public metadata and lets Gemini watch public URLs; we never download, reuse or re-upload their videos | radar |
| Shorts pay floor (Feb 1, 2027): 10M qualified views per 90 d | Shorts are reach; money plan includes long-form compilations | STRATEGY |
| YPP entry doubles Feb 1, 2027 (8,000 h or 20M Shorts views); partners already in stay in | Sprint to apply by mid-January under today's bar (S7) | STRATEGY, TEST-PLAN |
| YouTube's "AI slop" viewer survey; channel-level enforcement on recent uploads | Every upload holds the bar; a weak day posts nothing | QC, room |
| YPP reviewers and appeals ask how AI content was made | Keep each Short's script, prompts, refs, rejected takes and edit log (appeal pack) | generator ledger, `work/` sidecars |
| One termination bars every channel of the person | One channel: Peakz Recaps renamed Nine to Purr, its remakes deleted first; no backups (S8) | SETUP |
| Gemini/Omni terms | No recognizable people or minors as inputs; outputs carry SynthID | generator |
| Taxes | W-8BEN in AdSense before money arrives; contador for Paraguay IRP | SETUP |
