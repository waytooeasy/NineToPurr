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
    replies = {"j": '{"seen": 5, "font": "condensed", "case": "upper", "highlight": null, "header": "none"}',
               "c": 'ok {"seen": 2, "font": "geometric"}'}                                 # too few captions
    doc = SS.run(MARKET, {"Jynxzi": ["jynxzi"], "CaseOh": ["caseoh_"]}, tmp_path / "s.json",
                 vision=lambda imgs: replies[imgs[0][:1].decode()], grab=lambda ids: [i.encode() for i in ids][:5],
                 now=NOW, top=2)
    assert list(doc["streamers"]) == ["Jynxzi"]
    assert doc["streamers"]["Jynxzi"] == {"logins": ["jynxzi"], "images": 5, "caption": {
        "font": "condensed", "case": "upper", "highlight": None, "header": "none"}}
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
