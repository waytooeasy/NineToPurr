import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import upload as up

TZ = ZoneInfo("America/Asuncion")
CFG = up.Config()


def local(h, m=0, day=16):
    return datetime(2026, 10, day, h, m, tzinfo=TZ)


def utc_str(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class FakeHttpError(Exception):
    def __init__(self, status, reason):
        self.resp = type("R", (), {"status": status})()
        self.content = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode()


class Recorder:
    def __init__(self, fail=None, vid="VID1"):
        self.calls, self.fail, self.vid = [], fail, vid

    def __call__(self, path, body):
        self.calls.append((path, body))
        if self.fail:
            raise self.fail
        return self.vid


@pytest.fixture
def mp4(tmp_path):
    p = tmp_path / "c.mp4"
    p.write_bytes(b"x")
    return str(p)


@pytest.fixture
def alerts():
    class A(list):
        def __call__(self, text):
            self.append(text)

    return A()


def sent(alerts):
    return list(alerts)


# ---- schedule math

def test_slots_fresh_window_default_fits_four():
    slots = up.compute_slots(local(19, 5), [], CFG)
    assert [s.hour for s in slots] == [19, 21, 23, 1]  # 7 h window, 2 h gap
    assert up.slot_due(local(19, 5), slots)


def test_slots_five_with_longer_window():
    cfg = up.Config(window_end="03:00")
    assert len(up.compute_slots(local(19, 0), [], cfg)) == 5


def test_not_due_before_window_and_spacing():
    assert not up.slot_due(local(15), up.compute_slots(local(15), [], CFG))
    pub = [local(19, 10)]
    slots = up.compute_slots(local(20, 0), pub, CFG)
    assert slots[0] == local(21, 10)
    assert not up.slot_due(local(20, 0), slots)
    assert all(b - a >= timedelta(hours=2) for a, b in zip(slots, slots[1:]))


def test_window_crossing_midnight_uses_yesterdays_window():
    # 00:30 on the 17th still belongs to the window that began on the 16th
    pub = [local(19, 0), local(21, 0), local(23, 0)]
    now = local(1, 30, day=17)
    start, end = up.current_window(now, CFG)
    assert start == local(19, 0) and end == local(2, 0, day=17)
    slots = up.compute_slots(now, pub, CFG)
    assert slots == [local(1, 0, day=17)]
    assert up.slot_due(now, slots)


def test_after_window_end_waits_for_next_window():
    now = local(3, 0, day=17)
    start, _ = up.current_window(now, CFG)
    assert start == local(19, 0, day=17)
    assert not up.slot_due(now, up.compute_slots(now, [], CFG))


def test_max_per_day_cap():
    cfg = up.Config(max_per_day=2)
    assert up.compute_slots(local(23), [local(19), local(21)], cfg) == []


def test_overdue_first_slot_spaces_rest_from_now():
    slots = up.compute_slots(local(20, 30), [], CFG)
    assert slots[0] == local(19, 0)
    assert slots[1] == local(22, 30)


# ---- metadata

def test_metadata(con, add_clip):
    cid = add_clip(state="approved")
    con.execute("UPDATE clips SET hook_text='xhook', title=NULL WHERE id=?", (cid,))
    m = up.build_metadata(con.execute("SELECT * FROM clips WHERE id=?", (cid,)).fetchone(), CFG)
    assert m["snippet"]["title"] == "xhook"
    assert "Kai loses it" in m["snippet"]["description"] and "#Shorts" in m["snippet"]["description"]
    assert "#Shorts" in m["snippet"]["tags"] and m["snippet"]["categoryId"] == "20"
    long = "a" * 300
    con.execute("UPDATE clips SET title=? WHERE id=?", (long, cid))
    m = up.build_metadata(con.execute("SELECT * FROM clips WHERE id=?", (cid,)).fetchone(), CFG)
    assert len(m["snippet"]["title"]) == 100


# ---- run_once

def approved(con, add_clip, mp4):
    cid = add_clip(state="approved", path=mp4)
    return cid


def test_upload_flow_and_idempotency(con, add_clip, mp4, alerts):
    cid = approved(con, add_clip, mp4)
    rec = Recorder()
    now = local(19, 30)
    out = up.run_once(con, CFG, rec, alerts, now)
    assert "uploaded" in out and len(rec.calls) == 1
    row = con.execute("SELECT * FROM posts WHERE clip_id=?", (cid,)).fetchone()
    assert row["platform_post_id"] == "VID1" and row["url"].endswith("VID1")
    assert con.execute("SELECT state FROM clips WHERE id=?", (cid,)).fetchone()[0] == "published"
    acc = con.execute("SELECT platform FROM accounts WHERE id=?", (row["account_id"],)).fetchone()
    assert acc[0] == "youtube"

    # clip back at approved with a posts row: only marked published, no re-upload
    con.execute("UPDATE clips SET state='approved' WHERE id=?", (cid,))
    con.commit()
    up.run_once(con, CFG, rec, alerts, local(22, 0))
    assert len(rec.calls) == 1
    assert con.execute("SELECT state FROM clips WHERE id=?", (cid,)).fetchone()[0] == "published"
    assert con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1


def test_not_due_means_no_upload(con, add_clip, mp4, alerts):
    approved(con, add_clip, mp4)
    rec = Recorder()
    first = up.run_once(con, CFG, rec, alerts, local(19, 30))
    second = up.run_once(con, CFG, rec, alerts, local(20, 0))
    assert "uploaded" in first
    assert "no slot due" in second and len(rec.calls) == 1


def test_quota_stops_day_and_alerts(con, add_clip, mp4, alerts):
    c1 = approved(con, add_clip, mp4)
    c2 = approved(con, add_clip, mp4)
    rec = Recorder(fail=up.QuotaExceeded("quotaExceeded"))
    now = local(19, 30)
    assert "quota" in up.run_once(con, CFG, rec, alerts, now)
    assert len(sent(alerts)) == 1 and "quota" in sent(alerts)[0].lower()
    err = con.execute("SELECT last_error, state FROM clips WHERE id=?", (c1,)).fetchone()
    assert err["last_error"].startswith("quota:") and err["state"] == "approved"
    # later same day: no further API calls
    con.execute("UPDATE clips SET state_changed_at=? WHERE id=?", (utc_str(now), c1))
    rec2 = Recorder()
    assert "quota" in up.run_once(con, CFG, rec2, alerts, local(22, 0))
    assert rec2.calls == []
    # next day: tries again (clean clip first)
    out = up.run_once(con, CFG, rec2, alerts, local(19, 30, day=17))
    assert "uploaded" in out and rec2.calls[0][0] == mp4
    assert c2  # silence lint


def test_classify_quota_vs_other():
    assert isinstance(up.classify_error(FakeHttpError(403, "quotaExceeded")), up.QuotaExceeded)
    assert isinstance(up.classify_error(FakeHttpError(403, "uploadLimitExceeded")), up.QuotaExceeded)
    other = FakeHttpError(403, "forbidden")
    assert up.classify_error(other) is other
    e = ValueError("x")
    assert up.classify_error(e) is e


def test_other_error_does_not_block_other_clips(con, add_clip, mp4, alerts):
    bad = add_clip(state="approved", path="/nope/missing.mp4")
    good = add_clip(state="approved", path=mp4)
    rec = Recorder()
    out = up.run_once(con, CFG, rec, alerts, local(19, 30))
    assert "uploaded clip %d" % good in out
    assert "file missing" in con.execute("SELECT last_error FROM clips WHERE id=?", (bad,)).fetchone()[0]
    assert con.execute("SELECT state FROM clips WHERE id=?", (bad,)).fetchone()[0] == "approved"
    assert len(sent(alerts)) == 1


def test_upload_exception_recorded_and_failed_clip_goes_last(con, add_clip, mp4, alerts):
    c1 = approved(con, add_clip, mp4)
    c2 = approved(con, add_clip, mp4)
    out = up.run_once(con, CFG, Recorder(fail=RuntimeError("boom")), alerts, local(19, 30))
    assert "failed" in out
    assert "boom" in con.execute("SELECT last_error FROM clips WHERE id=?", (c1,)).fetchone()[0]
    assert [r["id"] for r in up.approved_clips(con)] == [c2, c1]


# ---- dry run, test upload, API wrapper, alerts

def test_dry_run_no_writes(con, add_clip, mp4):
    c1 = approved(con, add_clip, mp4)
    con.execute("UPDATE clips SET title='Kai wild' WHERE id=?", (c1,))
    con.commit()
    before = con.total_changes
    out = up.dry_run(con, CFG, local(19, 30))
    assert con.total_changes == before
    assert f"clip {c1}: Kai wild" in out and "19:00" in out and "(due)" in out
    assert con.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0


def test_test_upload(mp4):
    rec = Recorder(vid="T1")
    out = up.test_upload(mp4, "unlisted", CFG, uploader=rec)
    assert "T1" in out and "unlisted" in out
    assert rec.calls[0][1]["status"]["privacyStatus"] == "unlisted"
    with pytest.raises(FileNotFoundError):
        up.test_upload("/no/file.mp4", "public", CFG, uploader=rec)


def test_make_uploader_with_fake_service(monkeypatch, mp4):
    seen = {}

    class Req:
        def next_chunk(self):
            return None, {"id": "ABC"}

    class Videos:
        def insert(self, **kw):
            seen.update(kw)
            return Req()

    class Svc:
        def videos(self):
            return Videos()

    monkeypatch.setattr(up, "_media", lambda p: ("media", p))
    vid = up.make_uploader(CFG, service=Svc())(mp4, {"snippet": {}})
    assert vid == "ABC" and seen["part"] == "snippet,status" and seen["media_body"] == ("media", mp4)


def test_send_telegram_injectable():
    calls = []

    class R:
        ok = True

    def post(url, data, timeout):
        calls.append((url, data))
        return R()

    env = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_ALLOWED_CHAT_ID": "7"}
    assert up.send_telegram("hi", post=post, env=env)
    assert calls[0][0].endswith("/bottok/sendMessage") and calls[0][1]["chat_id"] == "7"
    assert not up.send_telegram("hi", post=post, env={})


def test_config_from_env():
    c = up.Config.from_env({"UPLOAD_MAX_PER_DAY": "3", "YOUTUBE_CATEGORY_ID": "24"})
    assert c.max_per_day == 3 and c.category_id == "24" and c.window_start == "19:00"
