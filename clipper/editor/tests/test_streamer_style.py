"""Per-streamer market look (editor/streamer_style.py, D49). Offline: fake thumbnails + fake vision."""
import json
from datetime import datetime, timedelta, timezone

import streamer_style as SS

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
MARKET = {"updated": "2026-10-20T10:00:00Z", "streamers": {
    "Jynxzi": {"demand_vph": 96000, "shorts": [{"id": f"j{i}", "en": True} for i in range(6)]},
    "CaseOh": {"demand_vph": 45000, "shorts": [{"id": f"c{i}", "en": True} for i in range(6)]},
    "Valkyrae": {"demand_vph": 300, "shorts": [{"id": "v1", "en": True}]},
}}


def test_run_writes_styles_for_top_streamers_with_enough_captioned_images(tmp_path):
    img = '{"captions": true, "font": "condensed", "case": "upper", "highlight": null, "header": "none", "words": 2}'
    replies = {"j": "[" + ",".join([img] * 4 + ['{"captions": true, "font": "geometric", "highlight": "#FF00FF",'
                                                 ' "header": "white_box", "words": 3}']) + "]",
               "c": '[{"captions": true, "font": "geometric"}, {"captions": false}]'}       # too few captions
    doc = SS.run(MARKET, {"Jynxzi": ["jynxzi"], "CaseOh": ["caseoh_"]}, tmp_path / "s.json",
                 vision=lambda imgs: replies[imgs[0][:1].decode()], grab=lambda ids: [i.encode() for i in ids][:5],
                 now=NOW, top=2)
    assert list(doc["streamers"]) == ["Jynxzi"]
    assert doc["streamers"]["Jynxzi"] == {"logins": ["jynxzi"], "images": 5, "seen": 5, "caption": {
        "font": "condensed", "case": "upper", "highlight": None, "words": 2, "header": "none"}}
    saved = json.loads((tmp_path / "s.json").read_text())
    assert saved["market"] == MARKET["updated"]
    assert SS.due(tmp_path / "s.json", MARKET["updated"], NOW + timedelta(hours=2)) is False
    assert SS.due(tmp_path / "s.json", "2026-10-21T10:00:00Z", NOW + timedelta(hours=2)) is True   # newer scan
    assert SS.due(tmp_path / "s.json", MARKET["updated"], NOW + timedelta(hours=25)) is True


def test_a_failing_streamer_is_skipped(tmp_path):
    def boom(imgs):
        raise RuntimeError("API down")
    doc = SS.run(MARKET, {}, tmp_path / "s.json", vision=boom, grab=lambda ids: [b"x"] * 5, now=NOW)
    assert doc["streamers"] == {}


def test_majority_needs_a_real_majority():
    per = [{"captions": True, "font": "condensed", "highlight": "#ff00ff", "header": "white_box", "words": 4},
           {"captions": True, "font": "condensed", "highlight": "#FF00FF", "header": "white_box", "words": 2},
           {"captions": True, "font": "geometric", "highlight": None, "header": "none", "words": 3},
           {"captions": False, "header": "none"}]
    d = SS.aggregate(per)
    assert d == {"seen": 3, "font": "condensed", "highlight": "#FF00FF", "words": 3, "header": "none"}  # 2/4 box: no
    per[3]["header"] = "white_box"
    assert SS.aggregate(per)["header"] == "white_box"


def test_no_clear_majority_keeps_yesterdays_look(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"streamers": {
        "Jynxzi": {"logins": ["jynxzi"], "caption": {"font": "condensed", "header": "none", "highlight": None}},
        "CaseOh": {"logins": ["caseoh_"], "caption": {"font": "geometric", "header": "white_box"}}}}))
    split = '[{"captions": true, "font": "condensed"}, {"captions": true, "font": "geometric"},' \
            ' {"captions": true, "font": "rounded"}, {"captions": true, "font": "other"}]'
    doc = SS.run(MARKET, {"Jynxzi": ["jynxzi"]}, p,
                 vision=lambda imgs: split if imgs[0][:1] == b"j" else "[]",
                 grab=lambda ids: [i.encode() for i in ids][:5], now=NOW, top=2)
    assert doc["streamers"]["Jynxzi"]["caption"]["font"] == "condensed"          # split today -> yesterday's
    assert doc["streamers"]["CaseOh"]["caption"]["header"] == "white_box"        # no read today -> kept
