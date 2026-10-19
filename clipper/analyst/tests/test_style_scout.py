"""Style scout: thumbnails -> style.json. Offline: fake HTTP and fake vision."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import style_scout  # noqa: E402

JPEG = b"\xff\xd8" + b"x" * 5000


class FakeHttp:
    def __init__(self, missing=()):
        self.urls, self.missing = [], set(missing)

    def get(self, url, timeout=None):
        self.urls.append(url)
        vid = url.split("/vi/")[1].split("/")[0]
        ok = vid not in self.missing and url.endswith("hq720.jpg")
        return NS(status_code=200 if ok else 404, content=JPEG if ok else b"")


def vision(seen, **cap):
    return lambda images: json.dumps({"seen": seen, "caption": cap, "layout": "fullbleed", "notes": "big caps"})


def test_writes_normalized_style(tmp_path):
    out = tmp_path / "style.json"
    doc = style_scout.run(["a", "b", "c", "d"], out, FakeHttp(missing={"b"}),
                          vision(3, case="upper", highlight="#00ff66", words=1, position="middle"))
    saved = json.loads(out.read_text())
    assert saved == doc and saved["sample"] == ["a", "c", "d"]
    assert saved["caption"]["highlight"] == "#00FF66" and saved["caption"]["words"] == 1


def test_keeps_old_style_when_few_captions(tmp_path):
    out = tmp_path / "style.json"
    out.write_text('{"old": true}')
    assert style_scout.run(["a", "b", "c"], out, FakeHttp(), vision(2, case="title")) is None
    assert json.loads(out.read_text()) == {"old": True}


def test_no_thumbnails_no_call(tmp_path):
    called = []
    assert style_scout.run(["a"], tmp_path / "s.json", FakeHttp(missing={"a"}),
                           lambda imgs: called.append(1)) is None and not called


def test_parse_tolerates_prose_around_json():
    assert style_scout.parse('Here you go: {"seen": 4} thanks') == {"seen": 4}
    assert style_scout.parse("no json") is None
