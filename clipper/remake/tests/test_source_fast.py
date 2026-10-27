"""#131: find the Short's stream fast, in partners' streams too, and give up within the search budget."""
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pytest

from remake import common as C
from remake import source

SR = source.LOC_SR


def stream(seconds, seed=0):
    return np.random.default_rng(seed).standard_normal(int(seconds * SR)).astype(np.float32)


@pytest.fixture
def fake_file(monkeypatch):
    """Audio 'files' are numpy arrays: C.read_audio / audio_duration slice them, no ffmpeg."""
    files, reads = {}, []

    def read(path, sr, start=None, dur=None, highpass=None, stereo=False):
        a = files[str(path)]
        i = int((start or 0) * sr)
        reads.append(start or 0)
        return a[i:] if dur is None else a[i:i + int(dur * sr)]
    monkeypatch.setattr(C, "read_audio", read)
    monkeypatch.setattr(source, "audio_duration", lambda path: len(files[str(path)]) / SR)
    return files, reads


def test_ncc_many_matches_one_needle_at_a_time():
    hay = stream(60, 1)
    needles = [hay[int(t * SR):int((t + 2) * SR)].copy() for t in (3.0, 20.5, 51.25)]
    many = source.ncc_many(hay, needles, {})
    for nd, (k, sc) in zip(needles, many):
        k1, sc1 = source.ncc_search(hay, nd)
        assert k == k1 and abs(sc - sc1) < 1e-4


def test_search_starts_right_before_the_short_and_stops_once_found(fake_file):
    files, reads = fake_file
    vod = stream(3 * 3600, 2)                    # a 3 h stream
    t = 2 * 3600 + 400.0                         # the moment, 2 h in
    files["vod"] = vod
    short = vod[int(t * SR):int((t + 30) * SR)].copy()
    hits = source.locate(short, "vod", 0.0, 3 * 3600, chunk_s=600.0, after_found_s=600.0)
    good = source._found(hits)
    assert good and all(abs(h["file_t"] - h["short_t"] - t) < 0.01 for h in good)
    assert min(reads) >= t - 1300               # the first two hours were never read
    assert hits.searched_s == 4200            # its last hour, the chunk with the moment, then 10 min more


def test_budget_gives_up_with_what_was_searched(fake_file, tmp_path, monkeypatch):
    files, _ = fake_file
    files["vod"] = stream(2 * 3600, 3)
    files[str(tmp_path / "short.mp4")] = stream(30, 4)                # not in this stream
    now = [0.0]

    def clock():
        now[0] += 100.0                                               # every chunk 'takes' 100 s
        return now[0]
    plans = [("v1", "x", None, None, (0.0, 7200.0)), ("v2", "x", None, None, (0.0, 7200.0))]
    monkeypatch.setattr(source, "download_audio", lambda vod_id, out, s=None, e=None: "vod")
    with pytest.raises(source.NotFound, match=r"no VOD audio matches S1 \(tried 1, gave up after 10 min"):
        source.find({"id": "S1", "published": "2026-10-27T12:00:00Z"}, tmp_path, plans=plans,
                    budget_s=600, clock=clock)


def test_only_the_stream_before_the_short_is_searched():
    start = datetime(2026, 10, 25, 21, 5, tzinfo=timezone.utc)
    pub = datetime(2026, 10, 25, 21, 45, tzinfo=timezone.utc)       # Emiru's Short went up 40 min into the stream
    assert source.before_publish(start, 8.4 * 3600, pub) == (0.0, 2400.0)
    assert source.before_publish(start, 3600, datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)) == (0.0, 3600.0)
    assert source.before_publish(start, 3600, datetime(2026, 10, 25, 20, 0, tzinfo=timezone.utc)) is None


class Tw:
    """Canned Helix: VOD 2907224886, the one #131 couldn't find for Agent00, is Kai Cenat's stream."""
    def __init__(self):
        self.calls = []

    def broadcaster_id(self, login):
        return login

    def _get(self, path, params):
        self.calls.append((path, params))
        if "id" in params:
            owner = {"2907224886": "KaiCenat", "2905313723": "agent00"}
            return {"data": [{"id": i, "user_login": owner[i]} for i in params["id"] if i in owner]}
        vods = {"agent00": [{"id": "2907100912", "created_at": "2026-10-21T21:23:33Z", "duration": "4h51m7s"}],
                "kaicenat": [{"id": "2907224886", "created_at": "2026-10-22T00:05:40Z", "duration": "5h36m0s"}]}
        return {"data": vods.get(params["user_id"], [])}


def test_agent00_shorts_search_kai_cenats_stream_after_his_own():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE remakes (short_id TEXT, streamer TEXT, status TEXT, vod_id TEXT)")
    con.executemany("INSERT INTO remakes VALUES (?,?,?,?)", [
        ("k6SwMP-29OU", "Agent00", "done", "2907224886"), ("mPDOCLV5V-s", "Agent00", "done", "2905313723"),
        ("x", "Agent00", "skipped", None)])
    source._VOD_OWNER.clear()
    tw = Tw()
    partners = source.partner_logins(con, tw, "Agent00", ["agent00"])
    assert partners == ["kaicenat"]
    plans = source.plans_for({"id": "AIJsi_csYws", "published": "2026-10-22T07:33:00Z"}, None, tw, ["agent00"],
                             partners=partners)
    assert [p[:2] for p in plans] == [("2907100912", "agent00"), ("2907224886", "kaicenat")]
    assert plans[1][4] == (0.0, 5 * 3600 + 36 * 60)                # Kai's stream had ended: all of it
    n = len(tw.calls)
    assert source.partner_logins(con, tw, "Agent00", ["agent00"]) == ["kaicenat"]
    assert len([c for c in tw.calls[n:] if "id" in c[1]]) == 0      # VOD owners asked once


def test_no_partners_without_twitch_or_finds():
    assert source.partner_logins(None, Tw(), "Agent00") == []
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE remakes (short_id TEXT, streamer TEXT, status TEXT, vod_id TEXT)")
    assert source.partner_logins(con, None, "Agent00") == []
    assert source.partner_logins(con, Tw(), "Agent00") == []
