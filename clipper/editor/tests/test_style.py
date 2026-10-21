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
                  "words": 3, "position": "middle", "font": "geometric", "header": "none", "highlight_on": True}
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


def test_palette_varies_per_clip_but_is_stable():
    st = S.normalize({"caption": {"highlights": ["#33ccff", "#99ff33", "#FFFFFF", "bad", "#33CCFF"]}})
    assert st["highlights"] == ["#33CCFF", "#99FF33"]             # valid, no fill, no dupes
    picks = {S.highlight_for(st, f"hook {i}") for i in range(20)}
    assert picks == {"#33CCFF", "#99FF33"}
    assert S.highlight_for(st, "same") == S.highlight_for(st, "same")


def test_onscreen_strips_emoji_keeps_text():
    assert S.onscreen("He really said never seen this 😭") == "He really said never seen this"
    assert S.onscreen("No way ❤️‍🩹 bro") == "No way bro"
    assert S.onscreen("Speed's $100 bet!") == "Speed's $100 bet!"
    assert S.onscreen("👍🏽") == "" and S.onscreen(None) == ""


def test_streamer_style_lays_over_the_global_one(tmp_path, monkeypatch):
    # 2026-10-20: CaseOh clippers use a white header box and no keyword colour; Jynxzi's a condensed font.
    g = tmp_path / "style.json"
    g.write_text(json.dumps({"caption": {"highlight": "#00BFFF", "highlights": ["#00BFFF", "#CCFF00"], "words": 3}}))
    sp = tmp_path / "styles.json"
    sp.write_text(json.dumps({"streamers": {
        "CaseOh": {"logins": ["caseoh_"], "caption": {"font": "geometric", "case": "title", "highlight": None,
                                                     "header": "white_box", "words": 2}},
        "Jynxzi": {"logins": ["jynxzi"], "caption": {"font": "condensed", "highlight": "#FF00FF", "position": "lower"}}}}))
    case = S.load(g, "caseoh_", sp)
    assert case["header"] == "white_box" and case["case"] == "title" and case["words"] == 2
    assert case["highlight_on"] is False and S.highlight_for(case, "x") == case["fill"]
    jyn = S.load(g, "Jynxzi", sp)
    assert jyn["font"] == "condensed" and S.font_for(jyn)[0] == "Anton" and jyn["position"] == "lower"
    assert jyn["highlight"] == "#FF00FF" and "highlights" not in jyn and jyn["words"] == 3   # rest from global
    other = S.load(g, "xqc", sp)
    assert other["font"] == "geometric" and other["highlights"] == ["#00BFFF", "#CCFF00"]
    assert S.version(g, "caseoh_", sp) != S.version(g, "xqc", sp) == S.version(g, None, sp)


def test_build_ass_white_box_header_and_condensed_font(tmp_path, monkeypatch):
    sp = tmp_path / "styles.json"
    sp.write_text(json.dumps({"streamers": {"CaseOh": {"logins": ["caseoh_"], "caption": {
        "font": "condensed", "header": "white_box", "highlight": None}}}}))
    monkeypatch.setenv("CLIPPER_STYLES", str(sp))
    ass = tmp_path / "a.ass"
    words = [{"s": 1, "e": 1.5, "w": "type"}, {"s": 1.5, "e": 2, "w": "timing"}]
    lay = {"mode": "stack", "cam": [0, 0, 400, 300], "cam_h": 768, "W": 1920, "H": 1080}
    clip.build_ass(words, {"start": 0, "end": 12, "hook": "W timing", "creator": "caseoh_", "layout": lay}, ass)
    txt = ass.read_text()
    assert "Style: Cap,Anton,124," in txt and ",3,16,0,5," in txt.split("Style: Head,")[1]   # opaque box style
    head = [l for l in txt.splitlines() if ",Head," in l]
    assert len(head) == 1 and "0:00:12.00" in head[0] and "\\pos(540,768)" in head[0]      # whole clip, on the seam
    caps = [l for l in txt.splitlines() if ",Cap," in l]
    assert caps and all("\\pos(540,1286)" in c for c in caps)                             # moved into the gameplay
    assert all("\\c&H" not in c.split("}", 2)[-1] for c in caps)                           # no keyword colour


def test_market_layout_per_streamer(tmp_path):
    import json
    import style as S
    sp = tmp_path / "styles.json"
    sp.write_text(json.dumps({"streamers": {"Stable Ronaldo": {"logins": ["stableronaldo"], "layout": "full",
                                                               "caption": {}}}}))
    assert S.market_layout("stableronaldo", sp) == "full" and S.market_layout("xqc", sp) is None


def test_market_layout_across_streamers(tmp_path):
    import json
    import style as S
    sp = tmp_path / "styles.json"
    sp.write_text(json.dumps({"streamers": {"A": {"layout": "fit"}, "B": {"layout": "stack"}, "C": {"layout": "fit"},
                                            "D": {}}}))
    assert S.market_layout_any(sp) == "fit" and S.market_layout_any(tmp_path / "none.json") is None
