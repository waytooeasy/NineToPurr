"""Re-render cuts the right moment: YouTube VOD captures are a window file, Twitch clips start at 0."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(1, str(Path(__file__).resolve().parents[2]))

import rerender  # noqa: E402
from radar import capture  # noqa: E402


def test_twitch_times_unchanged():
    assert rerender.window_pick_times({"start_s": 0, "end_s": 25.0, "source": "twitch"}) == (0, 25.0)


def test_youtube_times_shift_into_window():
    row = {"start_s": 3600.0, "end_s": 3645.0, "source": "youtube"}
    off = capture.section({"start": 3600.0, "end": 3645.0})[0]
    start, end = rerender.window_pick_times(row)
    assert off > 0 and (start, end) == (3600.0 - off, 3645.0 - off)
    assert end - start == 45.0


def test_youtube_near_vod_start_never_negative():
    start, end = rerender.window_pick_times({"start_s": 2.0, "end_s": 30.0, "source": "youtube"})
    assert start >= 0 and end - start == 28.0


def test_row_without_source_column_treated_as_twitch():
    assert rerender.window_pick_times({"start_s": 5, "end_s": 20}) == (5, 20)
