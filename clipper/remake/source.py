"""Where a clipper Short's footage lives in the streamer's own stream VOD (D58), and download it.

1. Candidate VODs: the VOD of the streamer's own clip matched to this Short (moment_matches, D54), else the
   streamer's (and any watchlist streamer named in the title) Twitch archives and YouTube live streams that overlap
   the 4 days before it posted. YouTube VOD ids carry a "yt:" prefix (IShowSpeed, Kai's YouTube channel).
2. Coarse locate: loud 2 s snippets of the Short's audio, normalised cross-correlation over the VOD audio.
3. Download only the VOD video around the found seconds (1080p60 sections); the exact map runs on those files.
"""
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yaml

from . import common as C

LOC_SR = 4000          # Hz for the coarse search
SNIP_S = 2.0           # snippet length
MIN_NC = 0.7           # a snippet counts as found at this normalised correlation
HINT_PAD_S = 600       # audio searched around a moment-match hint
MAX_SECTION_S = 720    # longest single video section downloaded
DENSE_PAD_S = 300      # dense audio pass: this far around the snippet hits
FRAGMENTS = 8          # parallel HLS fragments: a 10 h VOD's audio took 15+ min one fragment at a time
SEARCH_BUDGET_S = int(os.environ.get("REMAKE_SEARCH_BUDGET_S", "600"))   # give up on a Short's source after this
MAX_VODS = 4           # stream VODs searched per streamer (newest first, within the budget)
AFTER_FOUND_S = 1200   # once found, search this much more of the stream (a clipper jumps across minutes)
WATCHLIST = Path(__file__).resolve().parents[1] / "radar" / "config" / "watchlist.yaml"


class NotFound(RuntimeError):
    pass


class BotCheck(RuntimeError):
    """YouTube asks the VM to sign in ('confirm you're not a bot'): try again later (or refresh the cookie file)."""


COOKIES = "/opt/clipper/youtube_cookies.txt"
SHORT_DL_TIMEOUT_S = 180


def has_ipv6():
    """A real IPv6 route out (not just Tailscale's): a UDP connect sends nothing but needs a route."""
    import socket
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as so:
            so.connect(("2001:4860:4860::8888", 53))
        return True
    except OSError:
        return False


def youtube_auth():
    """Lucas's YouTube cookies for Short downloads (D59, Lucas: "use my cookies"), when the file is there.
    Only for the clipper Short itself (one download per remake); never logged."""
    p = os.environ.get("YTDLP_COOKIES", COOKIES)
    if not (p and Path(p).is_file() and Path(p).stat().st_size > 0):
        return []
    # yt-dlp writes the cookie jar back when it exits: give it a copy, so a killed run or a full disk can never
    # empty Lucas's file (it did on 2026-10-27)
    import shutil
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix="ytc_", suffix=".txt")
    os.close(fd)
    shutil.copyfile(p, tmp)
    os.chmod(tmp, 0o600)
    _TEMP_COOKIES.append(tmp)
    return ["--cookies", tmp]


_TEMP_COOKIES = []


def drop_temp_cookies():
    while _TEMP_COOKIES:
        Path(_TEMP_COOKIES.pop()).unlink(missing_ok=True)


def is_yt(vod_id):
    return str(vod_id).startswith("yt:")


def vod_url(vod_id):
    v = str(vod_id)
    return f"https://www.youtube.com/watch?v={v[3:]}" if is_yt(v) else f"https://www.twitch.tv/videos/{v}"


def yt_flags():
    """YouTube requests: IPv4 only while the VM has no IPv6 route, Lucas's cookie file (D59), polite pacing."""
    return [*([] if has_ipv6() else ["-4"]), *youtube_auth(), "--sleep-requests", "1", "--socket-timeout", "20"]


def watchlist_ids(platform, names, text="", wl_path=None):
    """Watchlist ids on `platform` for these names, plus any watchlist streamer named in `text` (title/description)."""
    cfg = yaml.safe_load(Path(wl_path or WATCHLIST).read_text()) or {}
    by_name = {}
    for e in cfg.get("streamers", []):
        if e.get("platform") == platform and not e.get("disabled"):
            by_name.setdefault(str(e["name"]), []).append(str(e["id"]))
    out = [i for n in names for i in by_name.get(n, [])]
    low = (text or "").lower()
    for n, ids in by_name.items():
        if re.search(r"\b" + re.escape(n.lower()) + r"\b", low) or any(
                re.search(r"\b" + re.escape(i.lower().lstrip("@")) + r"\b", low) for i in ids):
            out += ids
    return list(dict.fromkeys(out))


def youtube_handles(names, text="", wl_path=None):
    return watchlist_ids("youtube", names, text, wl_path)


def name_for(platform, ident, wl_path=None):
    cfg = yaml.safe_load(Path(wl_path or WATCHLIST).read_text()) or {}
    for e in cfg.get("streamers", []):
        if e.get("platform") == platform and str(e["id"]).lower() == str(ident).lower():
            return str(e["name"])
    return str(ident)


def twitch_logins(names, text="", wl_path=None):
    """Twitch logins for watchlist names, plus any watchlist streamer named in `text` (title/description)."""
    cfg = yaml.safe_load(Path(wl_path or WATCHLIST).read_text()) or {}
    by_name = {}
    for e in cfg.get("streamers", []):
        if e.get("platform") == "twitch" and not e.get("disabled"):
            by_name.setdefault(str(e["name"]), []).append(str(e["id"]).lower())
    out = [lg for n in names for lg in by_name.get(n, [])]
    low = (text or "").lower()
    for n, logins in by_name.items():
        if re.search(r"\b" + re.escape(n.lower()) + r"\b", low) or any(re.search(r"\b" + re.escape(lg) + r"\b", low) for lg in logins):
            out += logins
    return list(dict.fromkeys(out))


def moment_hint(con, short_id):
    """(vod_id, vod_offset, login) of the streamer's own clip matched to this Short (D54), else None."""
    if con is None:
        return None
    try:
        row = con.execute("SELECT r.video_id, r.vod_offset, r.creator, r.source FROM moment_matches m"
                          " JOIN radar_candidates r ON r.clip_id = m.clip_id"
                          " WHERE m.short_id = ? AND r.video_id IS NOT NULL AND r.source IN ('twitch', 'youtube')",
                          (short_id,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    vod = f"yt:{row[0]}" if row[3] == "youtube" else str(row[0])
    return (vod, int(row[1] or 0), row[2])


def _dur(s):
    """Twitch duration '3h2m1s' -> seconds."""
    return sum(int(n) * {"h": 3600, "m": 60, "s": 1}[u] for n, u in re.findall(r"(\d+)([hms])", s or ""))


def recent_vods(tw, login, published, days=4):
    """Archive VODs of `login` that were live within `days` before `published` (newest first)."""
    data = tw._get("videos", {"user_id": tw.broadcaster_id(login), "type": "archive", "first": 20}).get("data", [])
    out = []
    for v in data:
        start = datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
        dur = _dur(v.get("duration"))
        if start <= published and start + timedelta(seconds=dur) >= published - timedelta(days=days):
            out.append({"id": str(v["id"]), "login": login, "dur": dur, "start": start})
    return sorted(out, key=lambda x: x["start"], reverse=True)


def youtube_streams(handle, published, days=4, key=None, session=None, uploads=30):
    """Past live streams of a YouTube channel that were live within `days` before `published` (newest first).
    Data API only (3 units: channel -> uploads playlist -> videos). The channel's /streams tab via yt-dlp came back
    empty or hung from the VM (YouTube throttles the home IP, #64), so every IShowSpeed Short was skipped."""
    key = key or os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return []
    import requests
    sess = session or requests
    api = "https://www.googleapis.com/youtube/v3/"
    ch = sess.get(api + "channels", params={"part": "contentDetails", "forHandle": handle, "key": key},
                  timeout=30).json().get("items") or []
    if not ch:
        return []
    up = ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = sess.get(api + "playlistItems", params={"part": "contentDetails", "playlistId": up,
                                                    "maxResults": uploads, "key": key}, timeout=30).json().get("items") or []
    ids = [i["contentDetails"]["videoId"] for i in items]
    if not ids:
        return []
    data = sess.get(api + "videos", params={"part": "liveStreamingDetails", "id": ",".join(ids), "key": key},
                    timeout=30).json()
    out = []
    for it in data.get("items", []):
        ls = it.get("liveStreamingDetails") or {}
        if not ls.get("actualStartTime"):
            continue
        start = datetime.fromisoformat(ls["actualStartTime"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(ls["actualEndTime"].replace("Z", "+00:00")) if ls.get("actualEndTime") else published
        if start <= published and end >= published - timedelta(days=days):
            out.append({"id": f"yt:{it['id']}", "login": handle, "start": start, "dur": (end - start).total_seconds()})
    return sorted(out, key=lambda x: x["start"], reverse=True)


def download_short(short_id, out_dir, runner=subprocess.run):
    out = Path(out_dir) / "short.mp4"
    if not out.exists():
        try:   # -4 only while the VM has no IPv6 route (some YouTube video servers here answer on IPv6 only)
            r = runner([C.ytdlp(), *([] if has_ipv6() else ["-4"]), *youtube_auth(), "--sleep-requests", "1", "--socket-timeout", "20",
                        "--retries", "3", "--fragment-retries", "3", "-f", "bv*+ba/b", "--merge-output-format", "mp4",
                        "-o", str(out), f"https://www.youtube.com/shorts/{short_id}"],
                       capture_output=True, text=True, timeout=SHORT_DL_TIMEOUT_S)
        except subprocess.TimeoutExpired:   # this video's server is unreachable from here: next Short
            raise RuntimeError(f"YouTube download of {short_id} timed out after {SHORT_DL_TIMEOUT_S} s")
        if r.returncode != 0:
            err = (r.stderr or "")[-400:]
            if "not a bot" in err or "Sign in to confirm" in err or "429" in err:
                raise BotCheck(f"YouTube bot check on {short_id}")
            raise RuntimeError(f"yt-dlp {short_id}: {err.strip()[-200:]}")
    return out


VOD_CACHE_S = 6 * 3600     # a whole VOD's audio is reused this long (several popping Shorts come from one stream)


def vod_cache(vod_id):
    return C.root() / "_vods" / (re.sub(r"[^A-Za-z0-9_-]", "_", str(vod_id)) + ".m4a")


def download_audio(vod_id, out, start=None, end=None):
    """The VOD's audio (a window of it with start/end). A whole VOD's audio goes to the shared cache
    ($CLIPPER_REMAKE/_vods) and is reused by the next Short from the same stream. Returns the file to read."""
    out = Path(out)
    if start is None:
        cache = vod_cache(vod_id)
        if cache.exists() and time.time() - cache.stat().st_mtime < VOD_CACHE_S:
            return cache
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.unlink(missing_ok=True)
        out = cache
    if not out.exists():
        if is_yt(vod_id):
            cmd = [C.ytdlp(), *yt_flags(), "-N", str(FRAGMENTS), "-f", "ba[ext=m4a]/ba", "-o", str(out)]
        else:
            cmd = [C.ytdlp(), "-N", str(FRAGMENTS), "-f", "Audio_Only/audio_only/ba/worst", "-o", str(out)]
        if start is not None:
            cmd += ["--download-sections", f"*{int(max(0, start))}-{int(end)}"]
        subprocess.run(cmd + [vod_url(vod_id)], check=True, capture_output=True)
    return out


def download_video(vod_id, start, end, out):
    out = Path(out)
    if not out.exists():
        fmt = ["-f", "bv*[height<=1080]+ba/b[height<=1080]/b"] if is_yt(vod_id) else ["-f", "b[height<=1080]/b"]
        subprocess.run([C.ytdlp(), *(yt_flags() if is_yt(vod_id) else []), "-N", str(FRAGMENTS), *fmt,
                        "--download-sections", f"*{int(start)}-{int(end + 0.999)}",
                        "--merge-output-format", "mp4", "-o", str(out), vod_url(vod_id)],
                       check=True, capture_output=True)
    return out


def audio_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, check=True, text=True).stdout
    return float(out.strip() or 0)


def snippets(audio, sr, n=8, win=SNIP_S):
    """Start samples of up to `n` loud, non-overlapping snippets."""
    L = int(win * sr)
    if len(audio) < L:
        return [0]
    cand = sorted(((float(np.mean(audio[i:i + L] ** 2)), i) for i in range(0, len(audio) - L + 1, L // 2)), reverse=True)
    out = []
    for e, i in cand:
        if e <= 1e-8:
            break
        if all(abs(i - j) >= L for j in out):
            out.append(i)
        if len(out) >= n:
            break
    return sorted(out)


def ncc_many(hay, needles, cache=None):
    """[(index, score)] of each needle in `hay`, same as ncc_search per needle, with the haystack's FFT (and, via
    `cache`, the needles' FFTs) done once: the whole-VOD search spent most of its time redoing them."""
    if not needles:
        return []
    L = max(len(x) for x in needles)
    if len(hay) < L or L == 0:
        return [(0, -1.0)] * len(needles)
    n = 1 << int(np.ceil(np.log2(len(hay) + L)))
    H = np.fft.rfft(hay, n)
    cs = np.concatenate([[0.0], np.cumsum(hay.astype(np.float64) ** 2)])
    cache = {} if cache is None else cache
    out, floors = [], {}
    for j, nd in enumerate(needles):
        Ln = len(nd)
        if Ln == 0:
            out.append((0, -1.0))
            continue
        F = cache.get((j, n))
        if F is None:
            F = cache[(j, n)] = np.conj(np.fft.rfft(nd, n))
        c = np.fft.irfft(H * F, n)[:len(hay) - Ln + 1]
        loc = cs[Ln:] - cs[:-Ln]
        if Ln not in floors:
            floors[Ln] = 0.02 * float(np.median(loc)) + 1e-9   # silence must not win on a tiny denominator
        nc = c / (np.sqrt(np.maximum(loc, floors[Ln])) * (np.linalg.norm(nd) + 1e-9))
        k = int(np.argmax(nc))
        out.append((k, float(nc[k])))
    return out


def ncc_search(hay, needle):
    """(index, score): best normalised cross-correlation of `needle` inside `hay` (FFT)."""
    L = len(needle)
    if len(hay) < L or L == 0:
        return 0, -1.0
    n = 1 << int(np.ceil(np.log2(len(hay) + L)))
    c = np.fft.irfft(np.fft.rfft(hay, n) * np.conj(np.fft.rfft(needle, n)), n)[:len(hay) - L + 1]
    cs = np.concatenate([[0.0], np.cumsum(hay.astype(np.float64) ** 2)])
    loc = cs[L:] - cs[:-L]
    floor = 0.02 * float(np.median(loc)) + 1e-9   # silence must not win on a tiny denominator
    nc = c / (np.sqrt(np.maximum(loc, floor)) * (np.linalg.norm(needle) + 1e-9))
    k = int(np.argmax(nc))
    return k, float(nc[k])


def locate(short_audio, path, start=0.0, end=None, sr=LOC_SR, chunk_s=600.0, deadline=None, clock=time.monotonic,
           after_found_s=AFTER_FOUND_S):
    """Coarse map of loud Short snippets inside the audio file: [{'short_t', 'file_t', 'nc'}].
    Searches [start, end) from its end backwards: clippers post within hours of the moment, so the stream right
    before the Short comes first. Stops `after_found_s` past the chunk where the Short was found, and at `deadline`
    (on `clock`) with what was searched so far. `.searched_s` on the result says how much that was."""
    idx = snippets(short_audio, sr)
    snips = [short_audio[i:i + int(SNIP_S * sr)] for i in idx]
    best = [(-1.0, 0.0)] * len(snips)
    end = audio_duration(path) if end is None else end
    t, stop_at, cache = end, None, {}

    def hits():
        return _Hits({"short_t": idx[k] / sr, "file_t": best[k][1], "nc": best[k][0]} for k in range(len(snips)))

    while t > start:
        t0 = max(start, t - chunk_s)
        a = C.read_audio(path, sr, start=t0, dur=t - t0 + SNIP_S, highpass=120)
        for k, (i, sc) in enumerate(ncc_many(a, snips, cache)):
            if sc > best[k][0]:
                best[k] = (sc, t0 + i / sr)
        t = t0
        if stop_at is None and _found(hits()):
            stop_at = t0 - after_found_s
        if (stop_at is not None and t <= stop_at) or (deadline is not None and clock() > deadline):
            break
    out = hits()
    out.searched_s = end - t
    return out


class _Hits(list):
    searched_s = 0.0


def sections_for(offsets, dur, pad=20.0):
    """VOD windows [(start, end)] covering every found offset (offset = vod_t - short_t) plus the Short's length."""
    offs = sorted(offsets)
    groups, cur = [], [offs[0]]
    for o in offs[1:]:
        if o - cur[-1] > 300:
            groups.append(cur)
            cur = [o]
        else:
            cur.append(o)
    groups.append(cur)
    out = []
    for g in groups:
        s, e = max(0.0, g[0] - pad), g[-1] + dur + pad
        out.append((s, min(e, s + MAX_SECTION_S)))
    return out


def _found(hits, n_min=2):
    good = [h for h in hits if h["nc"] >= MIN_NC]
    return good if len(good) >= max(n_min, (len(hits) + 2) // 3) else None


_VOD_OWNER = {}


def partner_logins(con, tw, streamer, own=()):
    """Twitch logins whose streams this streamer's Shorts were found in before, most finds first. A collab: the
    Agent00 Shorts came from Kai Cenat's stream (#131), so his VODs are searched for Agent00's Shorts too."""
    if con is None or tw is None or not streamer:
        return []
    try:
        ids = [str(r[0]) for r in con.execute(
            "SELECT vod_id FROM remakes WHERE streamer = ? AND status = 'done' AND vod_id IS NOT NULL"
            " AND vod_id NOT LIKE 'yt:%'", (streamer,))]
        need = [i for i in dict.fromkeys(ids) if i not in _VOD_OWNER]
        for k in range(0, len(need), 100):
            for v in tw._get("videos", {"id": need[k:k + 100]}).get("data", []):
                _VOD_OWNER[str(v["id"])] = v["user_login"].lower()
    except Exception as e:  # noqa: BLE001 - no partners is the old behaviour
        C.log(f"partners of {streamer}: {e}")
        return []
    n = {}
    for i in ids:
        lg = _VOD_OWNER.get(i)
        if lg and lg not in own:
            n[lg] = n.get(lg, 0) + 1
    return sorted(n, key=lambda lg: -n[lg])


def before_publish(start, dur, published):
    """(w0, w1): the part of a stream VOD that was live before the Short went up (seconds into the VOD).
    The moment can't be later than that, and searching the rest cost up to 20 min on a 48 h stream."""
    w1 = min(float(dur), (published - start).total_seconds())
    return (0.0, w1) if w1 > 0 else None


def plans_for(short, con=None, tw=None, logins=(), handles=(), yt_streams=youtube_streams, partners=()):
    """VOD windows to search, best first: [(vod_id, login, start|None, end|None, search window|None)]. Known before
    any download, so a Short whose streamer has no stream VOD around it is skipped without fetching anything.
    The moment-match hint first, then the streamer's Twitch archives, YouTube live streams (IShowSpeed, Kai's
    YouTube channel), then partners' archives (streams the streamer's Shorts were found in before, #131)."""
    plans = []
    hint = moment_hint(con, short["id"])
    if hint:
        vod_id, off, login = hint
        plans.append((vod_id, login, max(0, off - HINT_PAD_S), off + HINT_PAD_S))
    published = datetime.fromisoformat(short["published"].replace("Z", "+00:00")).astimezone(timezone.utc)
    def twitch(names):
        for login in names:
            try:
                for v in recent_vods(tw, login, published)[:MAX_VODS]:
                    w = before_publish(v["start"], v["dur"], published)
                    if w:
                        plans.append((v["id"], login, None, None, w))
            except Exception as e:  # unknown login, API hiccup: try the next
                C.log(f"vods for {login}: {e}")
    if tw is not None:
        twitch(logins)
    for handle in handles:
        try:
            for v in yt_streams(handle, published)[:MAX_VODS]:
                w = before_publish(v["start"], v["dur"], published)
                if w:
                    plans.append((v["id"], handle, None, None, w))
        except Exception as e:  # noqa: BLE001 - yt-dlp / API hiccup: try the next
            C.log(f"youtube streams for {handle}: {e}")
    if tw is not None:
        twitch([p for p in partners if p not in logins])
    return plans


def find(short, work, con=None, tw=None, logins=(), plans=None, handles=(), budget_s=None, clock=time.monotonic):
    """Locate the Short in a VOD and download the video sections. Returns
    {'vod_id', 'login', 'sections': [{'file', 'vod_s', 'vod_e'}], 'hits': [...]}; raises NotFound, also when the
    search has used `budget_s` (a Short that isn't in these streams cost up to an hour before #131)."""
    work = Path(work)
    short_audio = C.read_audio(work / "short.mp4", LOC_SR, highpass=120)
    dur = len(short_audio) / LOC_SR
    tried, searched = [], 0.0
    budget_s = SEARCH_BUDGET_S if budget_s is None else budget_s
    deadline = clock() + budget_s
    plans = plans if plans is not None else plans_for(short, con, tw, logins, handles)
    for p in plans:
        vod_id, login, s, e = p[:4]
        win = p[4] if len(p) > 4 and s is None else None
        if (vod_id, s) in tried:
            continue
        if clock() > deadline:
            raise NotFound(f"no VOD audio matches {short['id']} (tried {len(tried)}, gave up after "
                           f"{budget_s / 60:.0f} min with {searched / 3600:.1f} h of stream searched)")
        tried.append((vod_id, s))
        audio = work / (f"vod_{vod_id}_{int(s)}.m4a" if s is not None else f"vod_{vod_id}.m4a")
        try:
            audio = download_audio(vod_id, audio, s, e)
        except subprocess.CalledProcessError as err:
            C.log(f"audio download failed for VOD {vod_id}: {err.stderr[-300:] if err.stderr else err}")
            continue
        hits = locate(short_audio, audio, *(win or (0.0, None)), deadline=deadline, clock=clock)
        searched += hits.searched_s
        base = s or 0.0
        for h in hits:
            h["vod_t"] = base + h["file_t"]
        good = _found(hits)
        C.log(f"VOD {vod_id} ({login}): {sum(h['nc'] >= MIN_NC for h in hits)}/{len(hits)} snippets found")
        if not good:
            continue
        offs = [h["vod_t"] - h["short_t"] for h in good]
        try:   # every part of the Short, not only its loud snippets (a clipper jumps across minutes)
            from . import amap as A
            # only around what the snippets found: a whole VOD's audio (10 h) would not fit in memory
            w0 = max(0.0, min(offs) - base - DENSE_PAD_S)
            w1 = max(offs) - base + dur + DENSE_PAD_S
            rows = A.dense(short_audio, [C.read_audio(audio, LOC_SR, start=w0, dur=w1 - w0, highpass=120)], sr=LOC_SR)
            dense = [base + w0 + o for t, k, o, nc in rows if k is not None and nc >= A.MIN_NC]
            votes = {}
            for o in dense:
                votes[round(o)] = votes.get(round(o), 0) + 1
            offs += [o for o in dense if votes[round(o)] >= 2]   # one stray window is not a section
        except Exception as e:  # noqa: BLE001 - the snippets alone still give a window
            C.log(f"dense locate failed: {e}")
        secs = []
        for k, (a, b) in enumerate(sections_for(offs, dur)):
            f = download_video(vod_id, a, b, work / f"sec{k}_{vod_id}_{int(a)}_{int(b)}.mp4")
            secs.append({"file": str(f), "vod_s": a, "vod_e": b})
        owner = name_for("youtube", login) if is_yt(vod_id) else login
        return {"vod_id": vod_id, "login": login, "owner": owner, "platform": "youtube" if is_yt(vod_id) else "twitch",
                "sections": secs, "hits": hits}
    raise NotFound(f"no VOD audio matches {short['id']} (tried {len(tried)}, {searched / 3600:.1f} h of stream searched)")
