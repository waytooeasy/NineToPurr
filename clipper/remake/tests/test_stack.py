"""Stacked / overlay layouts (#130): synthetic stream + their Short made of two crops of the same stream frame
(facecam band over a gameplay band, a facecam box over gameplay), mapped by vmap.build and rebuilt by compose.
Offline: synthetic frames, ffmpeg for the short videos."""
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER)]
from remake import look, panels, render, vmap  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg")

FPS, NF = 30, 12
SW, SH = 960, 540            # the stream (section) at its native size = vmap's analysis width
OW, OH = 540, 960            # their Short (9:16) = vmap's analysis width
SEAM = 460                   # their rows 0..459: facecam, 460..: gameplay


def canvas(seed=7, w=1100, h=600):
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 110, np.uint8)
    for _ in range(1400):
        x, y, r = int(rng.integers(0, w)), int(rng.integers(0, h)), int(rng.integers(3, 22))
        col = tuple(int(v) for v in rng.integers(0, 255, 3))
        cv2.circle(img, (x, y), r, col, -1)
        cv2.rectangle(img, (x, y), (x + r, y + r // 2), tuple(255 - c for c in col), 2)
    return img


def stream_frames():
    """A still background with things moving on it (people, gameplay): every frame differs, no frame is a shifted
    copy of another (a pure pan would let any section frame match with a shifted crop)."""
    c = canvas()[0:SH, 0:SW]
    rng = np.random.default_rng(11)
    pos = rng.integers(0, [SW, SH], (60, 2)).astype(np.float64)
    vel = rng.normal(0, 7, (60, 2))
    col = rng.integers(0, 255, (60, 3))
    out = []
    for i in range(NF):
        f = c.copy()
        for p, v, cl in zip(pos, vel, col):
            x, y = (p + v * i).astype(int)
            cv2.circle(f, (int(x) % SW, int(y) % SH), 14, tuple(int(a) for a in cl), -1)
        out.append(f)
    return out


def crop(frame, x, y, k, size):
    """Their pixels (u, v) = stream (x + u * k, y + v * k): a crop of the stream frame scaled up."""
    M = np.array([[k, 0, x], [0, k, y]], np.float64)
    return cv2.warpAffine(frame, M, size, flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)


FACE = (600, 20, 280 / OW)       # stream x, y, k of the facecam band
GAME = (150, 180, 370 / OW)      # ... of the gameplay band
FULL = (200, 40, 0.5)            # a single crop filling their frame


def stacked(f):
    out = np.empty((OH, OW, 3), np.uint8)
    out[:SEAM] = crop(f, *FACE, (OW, SEAM))
    x, y, k = GAME
    out[SEAM:] = crop(f, x, y, k, (OW, OH - SEAM))
    return out


def boxed(f, box=(40, 240, 300, 520)):
    """Gameplay filling the frame with a facecam box (their rows y0..y1, cols x0..x1) over it."""
    out = crop(f, *FULL, (OW, OH))
    y0, y1, x0, x1 = box
    out[y0:y1, x0:x1] = crop(f, 640, 30, 150 / (x1 - x0), (x1 - x0, y1 - y0))
    return out


def video(path, frames, fps=FPS):
    h, w = frames[0].shape[:2]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p",
                          str(path)], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()
    return str(path)


@pytest.fixture(autouse=True)
def fewer_probes(monkeypatch):
    monkeypatch.setattr(panels, "PROBES", 8)        # 12-frame Shorts: 8 samples are plenty (16 in production)


def build(tmp_path, their):
    sec = stream_frames()
    sp = video(tmp_path / "sec.mp4", sec)
    tp = video(tmp_path / "short.mp4", their)
    am = {"segments": [{"sec": 0, "t0": 0.0, "t1": NF / FPS, "off": 0.0, "gain": 1.0}]}
    vm = vmap.build(tp, [{"file": sp}], am, out_w=OW, workers=2)
    return vm, sec


def rebuilt_diff(vm, sec, their, n):
    shot = render.shot_at(vm, n)
    ours = render.compose(sec[n], vm, shot, n)
    a = cv2.GaussianBlur(their[n].astype(np.float32), (0, 0), 1.5)
    b = cv2.GaussianBlur(ours.astype(np.float32), (0, 0), 1.5)
    return np.abs(a - b).max(2)


def test_facecam_over_gameplay_becomes_one_stack_shot_with_two_panels(tmp_path):
    sec = stream_frames()
    their = [stacked(f) for f in sec]
    vm, sec = build(tmp_path, their)
    assert [s["layout"] for s in vm["shots"]] == ["stack"]
    shot = vm["shots"][0]
    assert len(shot["panels"]) == 2 and vm["stacked"] >= NF - 4
    top, bot = shot["panels"]
    assert abs(top["rect"][1] - SEAM / OH) < 0.006 and abs(bot["rect"][0] - SEAM / OH) < 0.006   # seam within 3 px
    assert top["rect"][0] == 0 and bot["rect"][1] == 1 and top["rect"][2] == 0 and top["rect"][3] == 1
    k, cx, cy = vmap.params_at(top, 6)
    assert abs(k - FACE[2]) < 0.005 and abs(cx - (FACE[0] + OW / 2 * FACE[2])) < 2
    k, cx, cy = vmap.params_at(bot, 6)
    assert abs(k - GAME[2]) < 0.005 and abs(cy - (GAME[1] + (OH / 2 - SEAM) * GAME[2])) < 3
    assert shot["fill"] is None
    d = rebuilt_diff(vm, sec, their, 6)
    assert np.mean(d < 18) > 0.97                       # our frame is theirs, both panels and the seam


def test_mixed_short_keeps_its_full_shot_full(tmp_path):
    sec = stream_frames()
    their = [stacked(f) if i < 6 else crop(f, *FULL, (OW, OH)) for i, f in enumerate(sec)]
    vm, sec = build(tmp_path, their)
    lays = [(s["layout"], s["n0"]) for s in vm["shots"]]
    assert [x for x, _ in lays] == ["stack", "full"] and abs(lays[1][1] - 6) <= 1
    full = vm["shots"][1]
    k, cx, cy = vmap.params_at(full, 10)
    assert abs(k - FULL[2]) < 0.005
    assert np.mean(rebuilt_diff(vm, sec, their, 3) < 18) > 0.97
    assert np.mean(rebuilt_diff(vm, sec, their, 10) < 18) > 0.97


def test_facecam_box_over_gameplay_is_drawn_on_top(tmp_path):
    sec = stream_frames()
    their = [boxed(f) for f in sec]
    vm, sec = build(tmp_path, their)
    assert {s["layout"] for s in vm["shots"]} == {"stack"}
    shot = vm["shots"][0]
    under, box = shot["panels"]
    assert under["rect"] == [0, 1, 0, 1]
    assert np.allclose(box["rect"], [40 / OH, 240 / OH, 300 / OW, 520 / OW], atol=0.01)
    assert np.mean(rebuilt_diff(vm, sec, their, 6) < 18) > 0.97


def test_single_crop_short_is_never_probed_into_a_stack(tmp_path):
    sec = stream_frames()
    their = [crop(f, *FULL, (OW, OH)) for f in sec]
    vm, _ = build(tmp_path, their)
    assert [s["layout"] for s in vm["shots"]] == ["full"] and vm["stacked"] == 0


# ---------------- pieces ----------------
def test_find_panels_reads_two_bands_and_their_crops():
    f = stream_frames()[4]
    g = lambda x: cv2.cvtColor(x, cv2.COLOR_BGR2GRAY)  # noqa: E731
    got = panels.find_panels(g(stacked(f)), g(f))
    assert len(got) == 2
    (r0, M0), (r1, M1) = got
    assert r0[0] <= 3 and abs(r0[1] - SEAM) < 14 and abs(r1[0] - SEAM) < 14 and r1[1] >= OH - 3
    assert abs(M0[0][0] - FACE[2]) < 0.01 and abs(M1[0][0] - GAME[2]) < 0.01
    assert not panels.same_crop(M0, M1, (OW, OH))


def test_seam_is_refined_to_the_pixel_where_the_crops_switch():
    f = stream_frames()[4]
    g = cv2.cvtColor(stacked(f), cv2.COLOR_BGR2GRAY)
    s = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    MA = np.array([[FACE[2], 0, FACE[0]], [0, FACE[2], FACE[1]]])
    MB = np.array([[GAME[2], 0, GAME[0]], [0, GAME[2], GAME[1] - SEAM * GAME[2]]])
    coarse = [[0, SEAM - 15, 0, OW], [SEAM + 12, OH, 0, OW]]
    errs = [panels.error_map(g, s, MA, coarse[0]), panels.error_map(g, s, MB, coarse[1])]
    R = panels.refine_edges(coarse, errs, None, OH, OW)
    assert abs(R[0][1] - SEAM) <= 1 and abs(R[1][0] - SEAM) <= 1 and R[0][0] == 0 and R[1][1] == OH


def test_samples_cluster_into_one_layout_and_odd_frames_drop():
    a = [[0, 0.48, 0, 1], [0.48, 1, 0, 1]]
    b = [[0, 0.49, 0, 1], [0.47, 1, 0, 1]]
    odd = [[0, 0.3, 0, 1], [0.3, 1, 0, 1]]
    groups = panels.cluster([("s1", a), ("s2", b), ("s3", odd)])
    assert len(groups) == 1 and len(groups[0]["members"]) == 2


def test_canonical_order_puts_a_box_after_the_panel_it_sits_on():
    assert panels.canon([[0.04, 0.25, 0.55, 0.95], [0, 1, 0, 1]]) == [1, 0]
    assert panels.canon([[0.5, 1, 0, 1], [0, 0.5, 0, 1]]) == [1, 0]


def test_one_panel_frame_inside_a_stacked_run_stays_stacked():
    A, B = [[0.5, 0, 600], [0, 0.5, 20]], [[0.7, 0, 150], [0, 0.7, 0]]
    recs = [(n, 0, n, 0, [A, B], [0.9, 0.9]) for n in range(10)]
    recs[5] = (5, 0, 5, 0, [A, None], [0.9, 0.2])
    kind = panels.classify(10, recs, set(range(10)), (OW, OH))
    assert all(k[0] == "stack" for k in kind)
    one = panels.classify(10, [(n, 0, n, 0, [A, A], [0.9, 0.9]) for n in range(10)], set(range(10)), (OW, OH))
    assert all(k[0] == "single" for k in one)            # same crop in both panels = a full frame


def test_compose_stack_draws_each_panel_and_the_fill():
    sec = stream_frames()[3]
    shot = {"n0": 0, "n1": 1, "seg": 0, "sec": 0, "off": 0.0, "layout": "stack", "fill": [0, 0, 255],
            "panels": [{"rect": [0, 0.45, 0, 1], "path": {"0": [FACE[2], FACE[0] + OW / 2 * FACE[2],
                                                                FACE[1] + OH / 2 * FACE[2]]}},
                       {"rect": [0.5, 1, 0, 1], "path": {"0": [GAME[2], GAME[0] + OW / 2 * GAME[2],
                                                               GAME[1] + (OH / 2 - SEAM) * GAME[2]]}}]}
    vm = {"out_w": OW, "out_h": OH, "fps": FPS, "nfr": 1, "shots": [shot], "frames": {},
          "sections": [{"file": "x", "fps": FPS, "w": SW, "h": SH}]}
    out = render.compose(sec, vm, shot, 0)
    their = stacked(sec)
    assert np.abs(out[:400].astype(int) - their[:400].astype(int)).max(2).mean() < 6
    assert np.abs(out[490:].astype(int) - their[490:].astype(int)).max(2).mean() < 6
    assert (out[440] == [0, 0, 255]).all()              # between the panels: the measured fill colour
    half = render.compose(cv2.resize(sec, (SW // 2, SH // 2)), vm, shot, 0, (OW // 2, OH // 2))
    assert np.abs(half[100].astype(int) - cv2.resize(their, (OW // 2, OH // 2))[100].astype(int)).max(1).mean() < 25
    m = look._valid(vm, shot, 0, OW, OH)
    assert not m[440].any() and m[100, 100] and m[700, 100]


def test_fit_band_over_a_solid_colour_is_drawn_with_that_colour():
    sec = np.zeros((1080, 1920, 3), np.uint8)
    sec[:] = (40, 200, 40)
    shot = {"n0": 0, "n1": 10, "seg": 0, "sec": 0, "off": 0.0, "layout": "fit",
            "path": {str(n): [1.458, 960, 540] for n in range(10)},
            "bg": {"rel": 0.97, "sigma": 20, "gain": 1.0, "color": [0, 0, 0]}}
    vm = {"out_w": 1080, "out_h": 1440, "fps": 60, "nfr": 10, "shots": [shot], "frames": {},
          "sections": [{"file": "x", "fps": 60, "w": 1920, "h": 1080}]}
    out = render.compose(sec, vm, shot, 0)
    top = int(720 - 540 / 1.458)
    assert out[top + 10, 540, 1] > 190 and out[top - 40, 540].max() == 0


def test_facecam_shown_seconds_later_than_the_gameplay_gets_its_own_time_offset(tmp_path, monkeypatch):
    """The clipper re-syncs the facecam reaction: from frame 6 on, the top band shows the stream 6 frames later than
    the bottom band (Jynxzi / iboclips, 2026-10-24: 2.25 s)."""
    monkeypatch.setattr(panels, "SHIFT_STEP", 2)      # 30 fps test stream: a fine coarse step
    n_sec, dm = 22, 6
    base = stream_frames()
    rng = np.random.default_rng(3)
    pos, vel = rng.uniform(0, [300, 260], (40, 2)), rng.normal(0, 9, (40, 2))
    col = rng.integers(0, 255, (40, 3))
    room = canvas(seed=21, w=300, h=260)
    sec = []
    for i in range(n_sec):
        f = base[i % NF].copy()
        cam = room.copy()                                 # the facecam corner: a person moving in a room
        for p, v, c in zip(pos, vel, col):
            x, y = (p + v * i).astype(int)
            cv2.circle(cam, (int(x) % 300, int(y) % 260), 18, tuple(int(a) for a in c), -1)
        f[10:270, 590:890] = cam
        sec.append(f)
    their = []
    for n in range(14):
        out = np.empty((OH, OW, 3), np.uint8)
        out[:SEAM] = crop(sec[n + (dm if n >= 6 else 0)], *FACE, (OW, SEAM))
        x, y, k = GAME
        out[SEAM:] = crop(sec[n], x, y, k, (OW, OH - SEAM))
        their.append(out)
    sp, tp = video(tmp_path / "sec.mp4", sec), video(tmp_path / "short.mp4", their)
    am = {"segments": [{"sec": 0, "t0": 0.0, "t1": 14 / FPS, "off": 0.0, "gain": 1.0}]}
    vm = vmap.build(tp, [{"file": sp}], am, out_w=OW, workers=2)
    assert [s["layout"] for s in vm["shots"]] == ["stack", "stack"]
    a, b = vm["shots"]
    assert abs(b["n0"] - 6) <= 1 and a["panels"][0]["dt"] is None and b["panels"][0]["dt"] == dm
    assert b["panels"][1]["dt"] is None
    assert render.panel_frames(vm, b, 10) == {0: 10 + dm}
    ours = render.compose(sec[render.sec_frame_index(vm, b, 10)], vm, b, 10, shifted={0: sec[10 + dm]})
    d = np.abs(cv2.GaussianBlur(their[10].astype(np.float32), (0, 0), 1.5)
               - cv2.GaussianBlur(ours.astype(np.float32), (0, 0), 1.5)).max(2)
    assert np.mean(d < 18) > 0.97
