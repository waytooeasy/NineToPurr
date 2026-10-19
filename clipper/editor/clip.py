#!/usr/bin/env python3
"""
clip.py - long video -> captioned 9:16 vertical clips, ready to post.

Pipeline:
  1. yt-dlp downloads the source (YouTube/Twitch/Kick VOD URL or local file)
  2. faster-whisper transcribes with word-level timestamps
  3. Moment picking:
       a) --auto      : writer.py (Claude Haiku via llm()) scores transcript windows and
                        writes hooks + context line + title (needs ANTHROPIC_API_KEY)
       b) default     : writes transcript.txt -> paste into Claude chat ->
                        save the JSON answer as picks.json -> run again with --picks
  4. ffmpeg cuts each pick, makes it 9:16 (blurred background fill), burns
     word-pop captions + the hook text at the top
  5. Appends every clip to clips_log.csv (the tracking sheet)

Install (once):
  pip install yt-dlp faster-whisper anthropic requests
  + ffmpeg on PATH  (winget install ffmpeg / brew install ffmpeg / apt install ffmpeg)

Usage:
  python clip.py URL                      # download + transcribe, writes transcript.txt
  python clip.py URL --picks picks.json   # render the clips you picked
  python clip.py URL --auto -n 5 --creator "Kai Cenat"   # Writer picks 5 and renders them
  python clip.py --picks picks.json --auto               # Radar picks (D23): one source_url per pick,
                                                         # Writer drafts each, DB states follow

picks.json format:
  [{"start": 123.4, "end": 151.0, "hook": "He did NOT expect that",
    "context_line": "Kai just lost his bet to chat", "title": "..."}]
Radar picks carry {"source_url", "creator", "clip_id", "start", "end"} instead (D23): start/end are
seconds inside source_url. With --auto the Writer fills hook/context_line/title.
When the DB (CLIPPER_DB, default /opt/clipper/db/clip.db) has a clips row for the pick, the Writer
output is stored there (D24) and the state moves captured -> drafted -> edited. CSV = debug log only.
Every clip is hard-capped at 60 s (D8) and shows hook + context line (D7).
"""
import argparse, csv, datetime, json, os, re, sqlite3, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

MAX_CLIP_S = 60.0
MAX_TRIM_S = 2.0  # market window: viewers already chose this moment; trim at most dead air per end
WINDOW_S, STRIDE_S = 120.0, 90.0   # transcript windows sent to the Writer


DEFAULT_DB = "/opt/clipper/db/clip.db"


def work_root():
    """Per-clip work dirs (words.json, transcript, .ass) live under $CLIPPER_WORK; relative `work` if unset."""
    return Path(os.environ.get("CLIPPER_WORK", "work"))


def db_open():
    """Open $CLIPPER_DB; None when the file does not exist (stand-alone use without the DB)."""
    path = os.environ.get("CLIPPER_DB", DEFAULT_DB)
    if not Path(path).exists():
        print(f"no DB at {path}: skipping DB writes", file=sys.stderr)
        return None
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def clip_row(con, pick):
    """clips.id Radar created for this pick (radar_candidates.clips_id), or None."""
    if con is None or not pick.get("clip_id"):
        return None
    row = con.execute("SELECT clips_id FROM radar_candidates WHERE clip_id=?", (pick["clip_id"],)).fetchone()
    return row[0] if row else None


def captured_file(con, row_id):
    row = con.execute("SELECT file_path FROM clips WHERE id=?", (row_id,)).fetchone() if row_id else None
    return row[0] if row and row[0] and Path(row[0]).exists() else None


def _move(con, row_id, sets, params, from_states, to_state):
    marks = ",".join("?" * len(from_states))
    cur = con.execute(
        f"UPDATE clips SET {sets}, state=?, state_changed_at=datetime('now'), last_error=NULL "
        f"WHERE id=? AND state IN ({marks})", (*params, to_state, row_id, *from_states))
    con.commit()
    if cur.rowcount == 0:
        print(f"clips.id={row_id} not in {from_states}: state left alone", file=sys.stderr)
    return cur.rowcount == 1


def save_draft(con, row_id, pick):
    """After the Writer (D24): Writer output -> clips, captured -> drafted."""
    hooks = pick.get("hooks") or ([pick["hook"]] if pick.get("hook") else [])
    mr = pick.get("music_risk")
    return _move(con, row_id,
                 "model_score=?, context_line=?, hooks_json=?, hook_text=?, title=?, music_risk=?, "
                 "start_s=?, end_s=?",
                 (pick.get("score"), pick.get("context_line"), json.dumps(hooks), pick.get("hook"),
                  pick.get("title"), None if mr is None else int(bool(mr)), pick["start"], pick["end"]),
                 ("captured", "drafted"), "drafted")


def save_edited(con, row_id, mp4):
    """After render: drafted -> edited, file_path = the rendered Short."""
    return _move(con, row_id, "file_path=?", (str(mp4),), ("drafted",), "edited")


def run(cmd):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def download(src, work):
    if Path(src).exists():
        return Path(src)
    out = work / "source.mp4"
    if not out.exists():
        run(["yt-dlp", "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
             "--merge-output-format", "mp4", "-o", str(out), src])
    return out


def transcribe(video, work, model_size):
    cache = work / "words.json"
    if cache.exists():
        return json.loads(cache.read_text())
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    segments, _ = model.transcribe(str(video), word_timestamps=True, vad_filter=True)
    words, lines = [], []
    for seg in segments:
        lines.append(f"[{seg.start:.1f}-{seg.end:.1f}] {seg.text.strip()}")
        for w in seg.words or []:
            words.append({"s": w.start, "e": w.end, "w": w.word.strip()})
    cache.write_text(json.dumps(words))
    (work / "transcript.txt").write_text("\n".join(lines))
    return words


def windows(lines, size=WINDOW_S, stride=STRIDE_S):
    """Split '[s-e] text' transcript lines into overlapping time windows."""
    parsed = []
    for ln in lines:
        m = re.match(r"\[(\d+(?:\.\d+)?)-", ln)
        if m:
            parsed.append((float(m.group(1)), ln))
    if not parsed:
        return
    t, last = 0.0, parsed[-1][0]
    while t <= last:
        chunk = [ln for s0, ln in parsed if t <= s0 < t + size]
        if chunk:
            yield "\n".join(chunk)
        t += stride


def cap_pick(p):
    """Hard cap: never render more than 60 s."""
    p = dict(p)
    p["end"] = min(p["end"], p["start"] + MAX_CLIP_S)
    return p


def writer_picks(work, n, creator, meta=None):
    """Run the Writer on transcript windows; keep the n best, non-overlapping."""
    from writer import write_clip
    lines = (work / "transcript.txt").read_text().splitlines()
    plans = []
    for win in windows(lines):
        try:
            plans.append(write_clip(win, creator, meta))
        except Exception as e:  # one bad window must not kill the run
            print(f"writer skipped a window: {e}", file=sys.stderr)
    picks = []
    for pl in sorted(plans, key=lambda x: -x["score"]):
        if any(pl["in"] < q["end"] and q["start"] < pl["out"] for q in picks):
            continue
        picks.append(cap_pick({
            "start": pl["in"], "end": pl["out"], "hook": pl["hooks"][0], "hooks": pl["hooks"],
            "hook_variant": 0, "context_line": pl["context_line"], "title": pl["title"],
            "score": pl["score"], "music_risk": pl["music_risk"]}))
        if len(picks) == n:
            break
    (work / "picks.json").write_text(json.dumps(picks, indent=2))
    return picks


def market_window(pick, w_in, w_out, trim=MAX_TRIM_S):
    """Keep the length the market chose. A Radar pick is a moment viewers already clipped (Twitch) or
    replayed most (YouTube heatmap), so the Writer may only shave dead air: at most `trim` s per end.
    First VM pass: the Writer cut a 16.7 s clip to 3.4 s and a 37 s clip to 6 s."""
    s0, e0 = float(pick["start"]), float(pick["end"])
    start = min(max(s0, float(w_in)), s0 + trim)
    end = max(min(e0, float(w_out)), e0 - trim)
    if end - start <= 0:
        return s0, e0
    return start, end


def draft_pick(work, pick, creator, meta=None, clip_id=None):
    """Writer on the transcript inside one Radar pick -> pick with hook/hooks/context_line/title/score.
    `clip_id` = clips.id; tags the llm_usage rows."""
    from writer import write_clip
    lines = [ln for ln in (work / "transcript.txt").read_text().splitlines()
             if (m := re.match(r"\[(\d+(?:\.\d+)?)-", ln)) and pick["start"] <= float(m.group(1)) < pick["end"]]
    if not lines:
        raise ValueError("no transcript inside the pick")
    pl = write_clip("\n".join(lines), creator, meta, clip_id=clip_id)
    start, end = market_window(pick, pl["in"], pl["out"])
    return cap_pick({**pick, "start": start, "end": end, "hook": pl["hooks"][0], "hooks": pl["hooks"],
                     "hook_variant": 0, "context_line": pl["context_line"], "title": pl["title"],
                     "score": pl["score"], "music_risk": pl["music_risk"]})


def ass_time(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def esc(t):
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


def build_ass(words, pick, path, chunk=3):
    """Word-pop captions (3 words at a time, middle-lower screen) + hook on top."""
    start, end = pick["start"], pick["end"]
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial Black,92,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,7,2,2,60,60,560,1
Style: Hook,Arial Black,70,&H0000E5FF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,6,2,8,60,60,170,1
Style: Ctx,Arial,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,4,1,8,70,70,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    dur = end - start
    if pick.get("hook"):
        ev.append(f"Dialogue: 1,{ass_time(0)},{ass_time(min(dur, 4.0))},Hook,,0,0,0,,{esc(pick['hook'].upper())}")
    if pick.get("context_line"):
        # our angle (D7): who/why/what happened, under the hook, first 8 s
        ev.append(f"Dialogue: 1,{ass_time(0)},{ass_time(min(dur, 8.0))},Ctx,,0,0,0,,{esc(pick['context_line'])}")
    if pick.get("es_words"):
        # translated captions: spread evenly over the clip
        toks = pick["es_words"].split()
        groups = [toks[i:i + chunk] for i in range(0, len(toks), chunk)]
        step = dur / max(len(groups), 1)
        for i, g in enumerate(groups):
            ev.append(f"Dialogue: 0,{ass_time(i*step)},{ass_time((i+1)*step)},Cap,,0,0,0,,{esc(' '.join(g).upper())}")
    else:
        ws = [w for w in words if w["s"] >= start and w["e"] <= end and w["w"]]
        for i in range(0, len(ws), chunk):
            g = ws[i:i + chunk]
            t0 = g[0]["s"] - start
            t1 = (ws[i + chunk]["s"] - start) if i + chunk < len(ws) else g[-1]["e"] - start
            ev.append(f"Dialogue: 0,{ass_time(t0)},{ass_time(t1)},Cap,,0,0,0,,{esc(' '.join(w['w'] for w in g).upper())}")
    Path(path).write_text(head + "\n".join(ev) + "\n", encoding="utf-8")


def render(video, pick, ass, out):
    # 9:16: blurred full-frame background + sharp video centered, then captions
    vf = ("[0:v]split[a][b];"
          "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];"
          "[b]scale=1080:-2[fg];"
          "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
          f"ass='{Path(ass).as_posix().replace(':', chr(92) + ':')}'")
    pick = cap_pick(pick)
    run(["ffmpeg", "-y", "-ss", str(pick["start"]), "-t", f"{pick['end'] - pick['start']:.3f}", "-i", str(video),
         "-filter_complex", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", "-r", "30", "-movflags", "+faststart", str(out)])


def log(row, path="clips_log.csv"):
    p = Path(path)
    rows = []
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            if r.fieldnames == list(row):
                rows = None  # same header: just append
            else:
                rows = list(r)  # older header: rewrite with the new columns
    if rows is None:
        with open(p, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=list(row)).writerow(row)
        return
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row), restval="")
        w.writeheader()
        w.writerows(rows + [row])


def render_picks(src, picks, a, out, con=None, slug=None):
    """Download/transcribe `src`, then draft (Radar picks with --auto) and render each pick."""
    slug = slug or re.sub(r"[^A-Za-z0-9]+", "_", str(src))[-40:].strip("_") or "src"
    work = work_root() / str(slug)
    work.mkdir(parents=True, exist_ok=True)
    video = download(src, work)
    words = transcribe(video, work, a.model)
    meta = json.loads(a.meta)

    if picks is None:
        if a.auto:
            picks = writer_picks(work, a.n, a.creator, meta)
        else:
            print(f"\nTranscript ready: {work/'transcript.txt'}\n"
                  "Paste it into Claude, ask for picks in the picks.json format, "
                  "save as picks.json, then run again with --picks picks.json")
            return 0

    for i, p in enumerate(picks, 1):
        row = clip_row(con, p)
        try:
            if a.auto and p.get("source_url") and "hook" not in p:
                p = draft_pick(work, p, a.creator or p.get("creator", ""), {**meta, "clip_id": p.get("clip_id")},
                               clip_id=row)
            p = cap_pick(p)
            if row:
                save_draft(con, row, p)
            name = f"{slug}_{i:02d}_{a.lang}"
            ass = work / f"{name}.ass"
            mp4 = out / f"{name}.mp4"
            build_ass(words, p, ass)
            render(video, p, ass, mp4)
        except Exception as e:  # one bad pick must not kill the run
            print(f"pick {p.get('clip_id', i)} failed: {e}", file=sys.stderr)
            if row:
                con.execute("UPDATE clips SET last_error=?, state_changed_at=datetime('now') WHERE id=?",
                            (str(e)[:500], row))
                con.commit()
            continue
        if row:
            save_edited(con, row, mp4)
        (out / f"{name}.txt").write_text(p.get("title", ""), encoding="utf-8")
        log({"date": datetime.date.today().isoformat(), "campaign": a.campaign,
             "source": src, "clip_file": str(mp4), "start": p["start"], "end": p["end"],
             "hook": p.get("hook", ""), "lang": a.lang, "post_url": "",
             "views_24h": "", "views_72h": "", "usd": "",
             "hook_variant": p.get("hook_variant", ""), "context_line": p.get("context_line", ""),
             "title": p.get("title", ""), "score": p.get("score", ""),
             "music_risk": p.get("music_risk", "")})
    print(f"\nDone: {len(picks)} clips in {out}/ | debug log: clips_log.csv")
    return len(picks)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", help="video URL or local file (not needed when picks carry source_url)")
    ap.add_argument("--picks", help="picks.json to render")
    ap.add_argument("--auto", action="store_true", help="Writer (Claude Haiku) picks moments / drafts Radar picks")
    ap.add_argument("-n", type=int, default=5, help="clips to pick (auto mode)")
    ap.add_argument("--lang", default="en", choices=["en", "es"])
    ap.add_argument("--creator", default="", help="streamer name (auto mode; goes in the title)")
    ap.add_argument("--meta", default="{}", help="Radar metadata JSON for the Writer")
    ap.add_argument("--campaign", default="", help="campaign name for the log")
    ap.add_argument("--model", default="small", help="whisper size: base/small/medium")
    ap.add_argument("--out", default="clips")
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(exist_ok=True)
    picks = json.loads(Path(a.picks).read_text()) if a.picks else None

    if picks and all(p.get("source_url") for p in picks):  # Radar picks (D23): one source per pick
        con = db_open()
        for p in picks:
            row = clip_row(con, p)
            src = captured_file(con, row) or p["source_url"]
            render_picks(src, [p], a, out, con, slug=p.get("clip_id"))
        return
    if not a.src:
        ap.error("need a source URL/file, or --picks with source_url per pick")
    if a.auto and picks is None and not a.creator:
        ap.error("--auto needs --creator")
    render_picks(a.src, picks, a, out, db_open())


if __name__ == "__main__":
    main()
