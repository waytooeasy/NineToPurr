"""Daily market caption style (editor/style.py)."""
import json

import clip
import style as S


def test_default_without_file(tmp_path):
    assert S.load(tmp_path / "none.json") == S.DEFAULT and S.version(tmp_path / "none.json") == "default"


def test_bad_values_fall_back_and_good_ones_apply(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"caption": {"case": "title", "fill": "#ffffff", "highlight": "#00ff66",
                                         "outline": "red", "words": 9, "position": "nowhere"}}))
    st = S.load(f)
    assert st == {"case": "title", "fill": "#FFFFFF", "highlight": "#00FF66", "outline": "#000000",
                  "words": 3, "position": "middle"}
    assert S.version(f) != "default" and len(S.version(f)) == 12


def test_invisible_highlight_is_fixed():
    assert S.normalize({"fill": "#FFE500", "highlight": "#FFE500"})["highlight"] == "#FFFFFF"


def test_ass_colour_is_bgr():
    assert S.ass_color("#FFE500") == "&H0000E5FF&" and S.ass_color("#00FF66") == "&H0066FF00&"


def test_build_ass_follows_the_style(tmp_path, monkeypatch):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"caption": {"case": "title", "highlight": "#00FF66", "words": 1,
                                         "position": "lower"}}))
    monkeypatch.setenv("CLIPPER_STYLE", str(f))
    ass = tmp_path / "a.ass"
    words = [{"s": 1, "e": 1.4, "w": "and"}, {"s": 1.4, "e": 2, "w": "zoom"}]
    clip.build_ass(words, {"start": 0, "end": 5}, ass)
    caps = [l for l in ass.read_text().splitlines() if ",Cap," in l]
    assert len(caps) == 2                                    # 1 word per line
    assert "\\pos(540,1300)" in caps[1] and "{\\c&H0066FF00&}Zoom" in caps[1]  # lower, green, Title case
