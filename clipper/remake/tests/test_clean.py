"""A remake must be as smooth as theirs and show no other app's UI (clip 33, Asmongold reacting to a TikTok)."""
import cv2
import numpy as np

from remake import clean

W, H = 90, 160


def scene(n, wobble=0.0, seed=0):
    """A still textured scene; `wobble` px of back-and-forth crop jitter like our noisy panel paths."""
    rng = np.random.default_rng(seed)
    tex = cv2.GaussianBlur((rng.random((H + 20, W + 20)) * 255).astype(np.float32), (0, 0), 1.5)
    out = []
    for i in range(n):
        d = wobble * (1 if i % 2 else -1) if wobble else 0.0
        M = np.float32([[1, 0, 10 + d], [0, 1, 10 + d * 0.5]])
        out.append(cv2.warpAffine(tex, M, (W, H), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR).astype(np.uint8))
    return out


def test_a_wobbling_remake_is_caught_and_a_steady_one_passes():
    files = {"theirs": scene(240), "wobbly": scene(240, wobble=1.2), "steady": scene(240)}
    read = lambda path, k, cnt, fps, size: np.array(files[path][k:k + cnt])   # noqa: E731
    assert clean.judder("theirs", "wobbly", 30, 240, (W, H), reader=read).startswith("judder:")
    assert clean.judder("theirs", "steady", 30, 240, (W, H), reader=read) is None


def test_a_panel_that_only_wobbles_within_noise_holds_one_crop_and_a_real_zoom_is_kept():
    from remake import panels
    rng = np.random.default_rng(1)
    noisy = np.column_stack([0.01 * rng.standard_normal(60), 960 + 3 * rng.standard_normal(60),
                             540 + 3 * rng.standard_normal(60)])
    held = panels.hold_if_still(noisy, 1920)
    assert np.allclose(held, held[0]) and abs(held[0][1] - 960) < 2
    zoom = np.column_stack([np.linspace(0, 0.3, 60), np.full(60, 960.0), np.full(60, 540.0)])
    assert np.allclose(panels.hold_if_still(zoom, 1920), zoom)


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
