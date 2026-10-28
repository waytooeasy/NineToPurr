"""Try first the popping Shorts whose stream footage we can find (2026-10-28: 0 of 33 overnight were made)."""
from remake import run
from remake.tests.test_remake import MARKET, NOW, db


def tries(c, streamer, channel, found, missed):
    for i in range(found):
        c.execute("INSERT INTO remakes (short_id, streamer, channel, status, vod_id) VALUES (?,?,?,?,?)",
                  (f"{streamer}{channel}f{i}", streamer, channel, "done", "1"))
    for i in range(missed):
        c.execute("INSERT INTO remakes (short_id, streamer, channel, status, last_error) VALUES (?,?,?,?,?)",
                  (f"{streamer}{channel}m{i}", streamer, channel, "skipped", "source: no VOD audio matches x (tried 3)"))


def test_a_findable_short_beats_a_more_popping_one_we_never_find():
    c = db()
    tries(c, "Stable Ronaldo", "SpecificMinds", 6, 0)
    tries(c, "Jynxzi", "c", 0, 12)
    got = run.candidates(MARKET, c, NOW, twitch_names={"Stable Ronaldo", "Jynxzi"})
    assert [s["id"] for s in got] == ["A", "B"]          # 9k/h found 6 of 6 > 12k/h found 0 of 12
    assert got[0]["p_found"] > 0.8 > 0.2 > got[1]["p_found"]


def test_a_clipper_channel_counts_inside_its_streamer():
    c = db()
    tries(c, "Jynxzi", "c", 0, 6)               # this clipper's Jynxzi Shorts: never in his streams
    tries(c, "Jynxzi", "iboclips", 6, 0)        # another clipper's: always
    ps, pc, base = run.found_rates(c)
    assert pc[("Jynxzi", "iboclips")] > ps["Jynxzi"] > pc[("Jynxzi", "c")]
    new = run.p_found({"streamer": "Jynxzi", "channel": "someone new"}, (ps, pc, base))
    assert new == ps["Jynxzi"]                  # a new clipper starts at its streamer's rate


def test_download_breakage_says_nothing_about_the_source_and_no_history_keeps_views_order():
    c = db()
    c.execute("INSERT INTO remakes (short_id, streamer, channel, status, last_error) VALUES "
              "('x','Jynxzi','c','failed','retry: cookie file was broken')")
    ps, pc, base = run.found_rates(c)
    assert "Jynxzi" not in ps and base == 1 / 3      # not a try: (0 found + 1) / (0 tries + 3)
    c.execute("DELETE FROM remakes")
    got = run.candidates(MARKET, c, NOW, twitch_names={"Stable Ronaldo", "Jynxzi"})
    assert [s["id"] for s in got] == ["B", "A"]
