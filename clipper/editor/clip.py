#!/usr/bin/env python3
"""
clip.py - long video -> captioned 9:16 vertical clips, ready to post.

Pipeline:
  1. yt-dlp downloads the source (YouTube/Twitch/Kick VOD URL or local file)
  2. faster-whisper transcribes with word-level timestamps
  3. Moment picking:
       a) --auto      : Claude API picks the best moments (needs ANTHROPIC_API_KEY)
       b) default     : writes transcript.txt -> paste into Claude chat ->
                        save the JSON answer as picks.json -> run again with --picks
  4. ffmpeg cuts each pick, makes it 9:16 (blurred background fill), burns
     word-pop captions + the hook text at the top
  5. Appends every clip to clips_log.csv (the tracking sheet)

Install (once):
  pip install yt-dlp faster-whisper anthropic
  + ffmpeg on PATH  (winget install ffmpeg / brew install ffmpeg / apt install ffmpeg)

Usage:
  python clip.py URL                      # download + transcribe, writes transcript.txt
  python clip.py URL --picks picks.json   # render the clips you picked
  python clip.py URL --auto -n 5          # Claude picks 5 and renders them
  python clip.py URL --auto --lang es     # Spanish captions (translated by Claude)

picks.json format:
  [{"start": 123.4, "end": 151.0, "hook": "He did NOT expect that", "title": "..."}]
"""
import argparse, csv, datetime, json, os, re, subprocess, sys
from pathlib import Path

PICK_PROMPT = """You pick viral short-form clips from a livestream/video transcript.
Rules:
- Each clip 15-55 seconds, self-contained (makes sense with zero context).
- Starts on the hook: the first 2 seconds must grab attention. No slow setup.
- Prefer: reactions, arguments, unexpected moments, funny lines, big claims.
- Return ONLY JSON: a list of {{"start": sec, "end": sec, "hook": "<=7 words on-screen text", "title": "<=60 char caption"}}.
- Pick the {n} best moments, best first.
{lang_rule}
Transcript (each line: [start-end] text):
{transcript}"""


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


def claude_picks(work, n, lang):
    import anthropic
    lang_rule = ("- Also add \"es_words\": the clip's speech translated to natural Spanish, "
                 "as one string." if lang == "es" else "")
    prompt = PICK_PROMPT.format(n=n, lang_rule=lang_rule,
                                transcript=(work / "transcript.txt").read_text()[:180_000])
    msg = anthropic.Anthropic().messages.create(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"),
        max_tokens=4000, messages=[{"role": "user", "content": prompt}])
    text = msg.content[0].text
    picks = json.loads(text[text.find("["): text.rfind("]") + 1])
    (work / "picks.json").write_text(json.dumps(picks, indent=2))
    return picks


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

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    dur = end - start
    if pick.get("hook"):
        ev.append(f"Dialogue: 1,{ass_time(0)},{ass_time(min(dur, 4.0))},Hook,,0,0,0,,{esc(pick['hook'].upper())}")
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
    run(["ffmpeg", "-y", "-ss", str(pick["start"]), "-to", str(pick["end"]), "-i", str(video),
         "-filter_complex", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", "-r", "30", "-movflags", "+faststart", str(out)])


def log(row, path="clips_log.csv"):
    new = not Path(path).exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="video URL or local file")
    ap.add_argument("--picks", help="picks.json to render")
    ap.add_argument("--auto", action="store_true", help="let Claude API pick moments")
    ap.add_argument("-n", type=int, default=5, help="clips to pick (auto mode)")
    ap.add_argument("--lang", default="en", choices=["en", "es"])
    ap.add_argument("--campaign", default="", help="campaign name for the log")
    ap.add_argument("--model", default="small", help="whisper size: base/small/medium")
    ap.add_argument("--out", default="clips")
    a = ap.parse_args()

    slug = re.sub(r"[^A-Za-z0-9]+", "_", a.src)[-40:].strip("_") or "src"
    work = Path("work") / slug
    work.mkdir(parents=True, exist_ok=True)
    out = Path(a.out); out.mkdir(exist_ok=True)

    video = download(a.src, work)
    words = transcribe(video, work, a.model)

    if a.picks:
        picks = json.loads(Path(a.picks).read_text())
    elif a.auto:
        picks = claude_picks(work, a.n, a.lang)
    else:
        print(f"\nTranscript ready: {work/'transcript.txt'}\n"
              "Paste it into Claude, ask for picks in the picks.json format, "
              "save as picks.json, then run again with --picks picks.json")
        return

    for i, p in enumerate(picks, 1):
        name = f"{slug}_{i:02d}_{a.lang}"
        ass = work / f"{name}.ass"
        mp4 = out / f"{name}.mp4"
        build_ass(words, p, ass)
        render(video, p, ass, mp4)
        (out / f"{name}.txt").write_text(p.get("title", ""), encoding="utf-8")
        log({"date": datetime.date.today().isoformat(), "campaign": a.campaign,
             "source": a.src, "clip_file": str(mp4), "start": p["start"], "end": p["end"],
             "hook": p.get("hook", ""), "lang": a.lang, "post_url": "",
             "views_24h": "", "views_72h": "", "usd": ""})
    print(f"\nDone: {len(picks)} clips in {out}/ | logged to clips_log.csv")


if __name__ == "__main__":
    main()
