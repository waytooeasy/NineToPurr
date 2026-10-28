"""A remake must be as smooth as theirs and show no other app's UI (clip 33, Asmongold reacting to a TikTok)."""
import numpy as np

from remake import clean

W, H = 90, 160


def pan(n, step=1, repeat_every=0, jump_every=0, seed=0):
    """Frames of a texture panning `step` px/frame; repeated frames and jumps like a video played in a stream."""
    rng = np.random.default_rng(seed)
    tex = (rng.random((H, W * 6)) * 255).astype(np.uint8)
    out, x = [], 0
    for i in range(n):
        if repeat_every and i % repeat_every == 1:
            out.append(out[-1].copy())
            continue
        x += step + (6 if jump_every and i % jump_every == 0 else 0)
        out.append(np.ascontiguousarray(tex[:, x % (W * 5): x % (W * 5) + W]))
    return out


def reader_of(frames):
    return lambda path, k, cnt, fps, size: np.array(frames[k:k + cnt])


def test_a_juddery_remake_is_caught_and_a_smooth_one_passes():
    theirs = pan(300)
    jerky = pan(300, repeat_every=3, jump_every=7, seed=0)
    files = {"theirs": theirs, "jerky": jerky, "same": pan(300)}
    read = lambda path, k, cnt, fps, size: np.array(files[path][k:k + cnt])   # noqa: E731
    assert clean.judder("theirs", "jerky", 30, 300, (W, H), reader=read).startswith("judder:")
    assert clean.judder("theirs", "same", 30, 300, (W, H), reader=read) is None
    rep, jps = clean.smoothness("jerky", 30, 300, (W, H), reader=read)
    assert rep > 0.25 and jps > 2


def test_another_apps_watermark_or_player_ui_is_caught_and_errors_never_block():
    jpeg = lambda a, b, t: b"jpg"    # noqa: E731
    seen = []

    def vision(images, prompt):
        seen.append((len(images), "TikTok" in prompt))
        return '{"extra": true, "what": "TikTok logo and a 0:02 / 0:31 progress bar"}'
    why = clean.foreign_ui("t.mp4", "o.mp4", 28.0, vision, jpeg=jpeg)
    assert why and "TikTok logo" in why and seen == [(3, True)]
    assert clean.foreign_ui("t", "o", 28.0, lambda i, p: '{"extra": false}', jpeg=jpeg) is None
    assert clean.foreign_ui("t", "o", 28.0, lambda i, p: (_ for _ in ()).throw(RuntimeError("api")), jpeg=jpeg) is None
