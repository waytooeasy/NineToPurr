"""Upload approved Shorts to YouTube on a spaced schedule (D8, D21).

    python upload.py                      run one pass: upload one clip if a slot is due
    python upload.py --dry-run            print today's schedule, no API calls, no DB writes
    python upload.py --test-upload F.mp4 --privacy unlisted    one-off D21 test, no DB
    python upload.py --auth               one-time OAuth consent, caches the token

Secrets only from env / files under /opt/clipper, never in git. Google libs are imported
lazily; the uploader and the alert sender are injectable so tests run offline.

Crash risk (documented, accepted): if the process dies after videos.insert returns but before
the posts row is committed, the clip stays `approved` and the next pass uploads it again
(duplicate video). The window is a few ms; the posts row + state flip are one transaction.
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from approvals import DEFAULT_DB, connect, record_error

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
APPROVED = "approved"
PUBLISHED = "published"
QUOTA_PREFIX = "quota:"
QUOTA_REASONS = {"quotaExceeded", "uploadLimitExceeded", "dailyLimitExceeded", "rateLimitExceeded"}


@dataclass
class Config:
    tz: str = "America/Asuncion"
    window_start: str = "19:00"
    window_end: str = "02:00"        # earlier than start = crosses midnight
    max_per_day: int = 6             # D8, D52
    min_gap_hours: float = 2.0
    category_id: str = "20"          # Gaming
    privacy: str = "public"
    channel_handle: str = "youtube-main"
    client_secret: str = "/opt/clipper/client_secret.json"
    token_file: str = "/opt/clipper/youtube_token.json"

    @classmethod
    def from_env(cls, env=None):
        e = os.environ if env is None else env
        c = cls()
        c.tz = e.get("UPLOAD_TZ", c.tz)
        c.window_start = e.get("UPLOAD_WINDOW_START", c.window_start)
        c.window_end = e.get("UPLOAD_WINDOW_END", c.window_end)
        c.max_per_day = int(e.get("UPLOAD_MAX_PER_DAY", c.max_per_day))
        c.min_gap_hours = float(e.get("UPLOAD_MIN_GAP_HOURS", c.min_gap_hours))
        c.category_id = e.get("YOUTUBE_CATEGORY_ID", c.category_id)
        c.privacy = e.get("UPLOAD_PRIVACY", c.privacy)
        c.channel_handle = e.get("YOUTUBE_CHANNEL_HANDLE", c.channel_handle)
        c.client_secret = e.get("YOUTUBE_CLIENT_SECRET", c.client_secret)
        c.token_file = e.get("YOUTUBE_TOKEN_FILE", c.token_file)
        return c


# ---------------------------------------------------------------- schedule (pure)

def _hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _parse_db_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=timezone.utc)


def current_window(now: datetime, cfg: Config):
    """(start, end) aware datetimes of the posting window that contains `now`, or the next one.
    Handles windows crossing midnight: at 01:00 the window that began yesterday is current."""
    tz = ZoneInfo(cfg.tz)
    now = now.astimezone(tz)
    s, e = _hm(cfg.window_start), _hm(cfg.window_end)

    def build(day):
        start = datetime.combine(day, s, tz)
        end_day = day if e > s else day + timedelta(days=1)
        return start, datetime.combine(end_day, e, tz)

    prev = build(now.date() - timedelta(days=1))
    if now <= prev[1]:
        return prev
    return build(now.date())


def compute_slots(now: datetime, published: list[datetime], cfg: Config) -> list[datetime]:
    """Remaining upload slots in the current window, earliest first.

    `published` = datetimes (aware) of posts already made. Only those inside the window count.
    Slots respect max_per_day and min_gap. The first slot is the earliest allowed moment
    (window start, or last post + gap); if that is <= now the slot is due. Later slots are spaced
    from max(first, now). Note: a 7 h window with a 2 h gap fits 4 slots, not 5.
    """
    start, end = current_window(now, cfg)
    gap = timedelta(hours=cfg.min_gap_hours)
    done = sorted(p.astimezone(start.tzinfo) for p in published if start <= p.astimezone(start.tzinfo) <= end)
    remaining = cfg.max_per_day - len(done)
    if remaining <= 0:
        return []
    first = start
    if done:
        first = max(start, done[-1] + gap)
    base = max(first, now.astimezone(start.tzinfo))
    slots = [first]
    while len(slots) < remaining:
        base = base + gap
        slots.append(base)
    return [t for t in slots if t <= end]


def slot_due(now: datetime, slots: list[datetime]) -> bool:
    return bool(slots) and slots[0] <= now


# ---------------------------------------------------------------- metadata

def build_metadata(clip, cfg: Config, privacy: str | None = None, streamer=None, market=None) -> dict:
    """videos.insert body. With `market` (publisher/hashtags.py) the title/description/tags carry
    today's market hashtags for `streamer` (Lucas 2026-10-19)."""
    title = (clip["title"] or clip["hook_text"] or "Short").strip().replace("\n", " ")
    title = title[:100].strip() or "Short"
    parts = [p for p in [(clip["context_line"] or "").strip()] if p]
    parts.append("#Shorts")
    tags = ["#Shorts"]
    topics = (clip["topic_tags"] if "topic_tags" in clip.keys() else None) or ""
    tags += [t.strip() for t in topics.split(",") if t.strip()]
    snippet = {"title": title, "description": "\n\n".join(parts), "tags": tags, "categoryId": cfg.category_id}
    if market is not None:
        import hashtags
        snippet = hashtags.apply(snippet, clip["context_line"], streamer, market)
    return {
        "snippet": snippet,
        "status": {"privacyStatus": privacy or cfg.privacy, "selfDeclaredMadeForKids": False},
    }


# ---------------------------------------------------------------- YouTube API

class QuotaExceeded(Exception):
    pass


def classify_error(exc: Exception) -> Exception:
    """Turn a googleapiclient HttpError (duck-typed) into QuotaExceeded when it is a quota 403."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 403:
        content = getattr(exc, "content", b"") or b""
        try:
            raw = content.decode() if isinstance(content, bytes) else str(content)
            errs = json.loads(raw).get("error", {}).get("errors", [])
            reasons = {x.get("reason") for x in errs}
        except (ValueError, AttributeError):
            reasons = set()
        if reasons & QUOTA_REASONS:
            return QuotaExceeded(", ".join(sorted(reasons & QUOTA_REASONS)))
    return exc


def get_credentials(cfg: Config, interactive: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(cfg.token_file):
        creds = Credentials.from_authorized_user_file(cfg.token_file, SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif interactive:
        flow = InstalledAppFlow.from_client_secrets_file(cfg.client_secret, SCOPES)
        creds = flow.run_local_server(port=0)
    else:
        raise RuntimeError(f"no usable YouTube token at {cfg.token_file}; run: python upload.py --auth")
    with open(cfg.token_file, "w") as f:
        f.write(creds.to_json())
    os.chmod(cfg.token_file, 0o600)
    return creds


def _media(path: str):
    from googleapiclient.http import MediaFileUpload
    return MediaFileUpload(path, mimetype="video/mp4", chunksize=-1, resumable=True)


def make_uploader(cfg: Config, service=None):
    """Return uploader(path, body) -> video_id. `service` is injectable (tests)."""
    def upload(path: str, body: dict) -> str:
        nonlocal service
        if service is None:
            from googleapiclient.discovery import build
            service = build("youtube", "v3", credentials=get_credentials(cfg), cache_discovery=False)
        try:
            req = service.videos().insert(part="snippet,status", body=body, media_body=_media(path))
            resp = None
            while resp is None:
                _, resp = req.next_chunk()
        except Exception as exc:  # noqa: BLE001
            raise classify_error(exc) from exc
        return resp["id"]
    return upload


# ---------------------------------------------------------------- alerts

def send_telegram(text: str, post=requests.post, env=None) -> bool:
    e = os.environ if env is None else env
    token, chat = e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_ALLOWED_CHAT_ID")
    if not token or not chat:
        print(f"[alert not sent, no Telegram env] {text}", file=sys.stderr)
        return False
    try:
        r = post(f"https://api.telegram.org/bot{token}/sendMessage",
                 data={"chat_id": chat, "text": text[:4000]}, timeout=20)
        return bool(getattr(r, "ok", True))
    except Exception as exc:  # noqa: BLE001  alert failure must never crash the run
        print(f"[alert failed] {type(exc).__name__}", file=sys.stderr)
        return False


# ---------------------------------------------------------------- DB side

def get_account_id(con, cfg: Config) -> int:
    con.execute("INSERT OR IGNORE INTO accounts (platform, handle, created_at) VALUES ('youtube', ?, datetime('now'))",
                (cfg.channel_handle,))
    return con.execute("SELECT id FROM accounts WHERE platform='youtube' AND handle=?",
                       (cfg.channel_handle,)).fetchone()[0]


def published_times(con) -> list[datetime]:
    rows = con.execute("SELECT posted_at FROM posts p JOIN accounts a ON a.id = p.account_id"
                       " WHERE a.platform = 'youtube'").fetchall()
    return [_parse_db_utc(r[0]) for r in rows]


def approved_clips(con):
    """Clean clips first, then clips that failed before (so one bad clip never blocks the rest)."""
    return con.execute("SELECT * FROM clips WHERE state = ?"
                       " ORDER BY (last_error IS NOT NULL), id", (APPROVED,)).fetchall()


def quota_stopped_today(con, now: datetime, cfg: Config) -> bool:
    tz = ZoneInfo(cfg.tz)
    rows = con.execute("SELECT state_changed_at FROM clips WHERE last_error LIKE ?",
                       (QUOTA_PREFIX + "%",)).fetchall()
    today = now.astimezone(tz).date()
    return any(r[0] and _parse_db_utc(r[0]).astimezone(tz).date() == today for r in rows)


def _fail(con, clip_id, msg, alert):
    record_error(con, clip_id, msg)
    alert(f"Upload problem, clip {clip_id}: {msg}")


def run_once(con, cfg: Config, uploader, alert, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if quota_stopped_today(con, now, cfg):
        return "quota hit earlier today, not uploading"
    slots = compute_slots(now, published_times(con), cfg)
    if not slot_due(now, slots):
        nxt = slots[0].isoformat(timespec="minutes") if slots else "next window"
        return f"no slot due (next: {nxt})"

    for clip in approved_clips(con):
        cid = clip["id"]
        existing = con.execute("SELECT id FROM posts WHERE clip_id = ?", (cid,)).fetchone()
        if existing:  # already uploaded in an earlier run: never re-upload
            con.execute("UPDATE clips SET state=?, state_changed_at=datetime('now') WHERE id=?", (PUBLISHED, cid))
            con.commit()
            continue
        path = clip["file_path"]
        if not path or not os.path.isfile(path):
            _fail(con, cid, f"file missing: {path}", alert)
            continue
        import hashtags
        streamer = hashtags.streamer_for(con, cid)
        market = hashtags.load()
        if streamer:
            market = {**market, "streamer_tags": hashtags.market_tags(streamer["name"])}
        meta = build_metadata(clip, cfg, streamer=streamer, market=market)
        try:
            vid = uploader(path, meta)
        except QuotaExceeded as exc:
            record_error(con, cid, f"{QUOTA_PREFIX} {exc}")
            alert(f"YouTube quota hit ({exc}). Uploads stopped for today. Clip {cid} stays approved.")
            return "quota exceeded, stopped for today"
        except Exception as exc:  # noqa: BLE001
            _fail(con, cid, f"upload failed: {type(exc).__name__}: {exc}", alert)
            return f"clip {cid} failed"  # one attempt per pass; next pass tries another clip first
        account_id = get_account_id(con, cfg)
        with con:  # posts row BEFORE/with state flip, one transaction
            con.execute(
                "INSERT INTO posts (clip_id, account_id, platform_post_id, url, posted_at, caption)"
                " VALUES (?,?,?,?,?,?)",
                (cid, account_id, vid, f"https://youtube.com/shorts/{vid}",
                 now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                 meta["snippet"]["description"]))
            con.execute("UPDATE clips SET state=?, state_changed_at=datetime('now'), last_error=NULL WHERE id=?",
                        (PUBLISHED, cid))
        return f"uploaded clip {cid}: https://youtube.com/shorts/{vid}"
    return "no approved clips to upload"


def dry_run(con, cfg: Config, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(cfg.tz)
    start, end = current_window(now, cfg)
    slots = compute_slots(now, published_times(con), cfg)
    clips = [c for c in approved_clips(con)
             if not con.execute("SELECT 1 FROM posts WHERE clip_id=?", (c["id"],)).fetchone()]
    lines = [f"Window {start:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M} ({cfg.tz}), "
             f"max {cfg.max_per_day}/day, gap {cfg.min_gap_hours:g} h",
             f"Now {now.astimezone(tz):%Y-%m-%d %H:%M}, approved clips waiting: {len(clips)}"]
    if quota_stopped_today(con, now, cfg):
        lines.append("Quota hit today: uploads stopped.")
    for i, slot in enumerate(slots):
        label = f"clip {clips[i]['id']}: {build_metadata(clips[i], cfg)['snippet']['title']}" if i < len(clips) else "(no clip)"
        lines.append(f"  {slot:%H:%M}{' (due)' if slot <= now else ''}  {label}")
    if not slots:
        lines.append("  no slots left in this window")
    return "\n".join(lines)


def test_upload(path: str, privacy: str, cfg: Config, uploader=None) -> str:
    """D21: one-off upload to confirm public visibility. No DB."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    uploader = uploader or make_uploader(cfg)
    body = {"snippet": {"title": "Clipper test upload", "description": "Test upload #Shorts",
                        "tags": ["#Shorts"], "categoryId": cfg.category_id},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    vid = uploader(path, body)
    return f"https://youtube.com/shorts/{vid} (privacy={privacy}). Open it logged out to check visibility."


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-upload", metavar="FILE")
    ap.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public")
    ap.add_argument("--auth", action="store_true", help="one-time OAuth consent")
    args = ap.parse_args(argv)
    cfg = Config.from_env()

    if args.auth:
        get_credentials(cfg, interactive=True)
        print(f"token saved to {cfg.token_file}")
        return 0
    if args.test_upload:
        print(test_upload(args.test_upload, args.privacy, cfg))
        return 0
    con = connect(os.environ.get("CLIPPER_DB", DEFAULT_DB))
    if args.dry_run:
        print(dry_run(con, cfg))
        return 0
    print(run_once(con, cfg, make_uploader(cfg), send_telegram))
    return 0


if __name__ == "__main__":
    sys.exit(main())
