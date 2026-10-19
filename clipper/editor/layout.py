"""9:16 layout like the top clip channels (format research, 2026-10-19: NexxoRecaps, StreamBellz).

- "crop":  full-bleed 9:16 cut of the source, centred on the streamer's face (IRL / just chatting).
- "stack": facecam on top, gameplay below, both full width (gaming with a corner facecam).
No blurred letterbox bars: none of the top channels use them.

`choose_layout()` is pure (tests need no OpenCV); `detect_layout()` samples frames with OpenCV's
YuNet face detector (model downloaded by setup.sh; OpenCV 5 dropped the Haar cascades).
No OpenCV, no model, no faces or any error -> centred crop.
"""
import json
import os
import subprocess
from statistics import median

OUT_W, OUT_H = 1080, 1920
CAM_H = 768                 # stack: default facecam panel height (40 %), gameplay gets the rest
CAM_H_MIN, CAM_H_MAX = 600, 960   # a found facecam box keeps its own shape within these
EDGE_RATIO = 4.0            # an overlay border is a column/row this many times sharper than median
FACECAM_MAX_H = 0.20        # a face smaller than this (share of frame height) ...
FACECAM_EDGE = 0.34         # ... with its centre in the outer third -> corner facecam
FACECAM_MIN_H = 0.045       # a corner face smaller than this is a mini cam over an event/IRL broadcast
                            # (Adin's 33 px cam, 2026-10-19): blown up it is mush, so full-bleed the shot
SAMPLES = 8
CLUSTER = 0.08              # detections within 8 % of the frame width are the same face
MODEL = "/opt/clipper/models/face_detection_yunet_2023mar.onnx"


def probe_size(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def choose_layout(faces, W, H, cam_box=None):
    """faces: [(x, y, w, h)] in source pixels from sampled frames (any number per frame).
    cam_box: the facecam overlay's (x0, y0, x1, y1) if its borders were found (find_cam_box)."""
    faces = dominant(faces, W)
    if not faces:
        return {"mode": "crop", "cx": W / 2, "W": W, "H": H}
    cx = median(x + w / 2 for x, y, w, h in faces)
    cy = median(y + h / 2 for x, y, w, h in faces)
    fh = median(h for x, y, w, h in faces)
    fw = median(w for x, y, w, h in faces)
    corner = (cx < W * FACECAM_EDGE or cx > W * (1 - FACECAM_EDGE)) and fh < H * FACECAM_MAX_H
    if not corner:
        return {"mode": "crop", "cx": cx, "W": W, "H": H}
    if fh < H * FACECAM_MIN_H:
        return {"mode": "crop", "cx": W / 2, "W": W, "H": H}
    if cam_box:
        return stack_from_box(cam_box, cx, cy, W, H)
    # no borders found: a few face-heights around the face, panel aspect 1080:768
    ch = min(H, fh * 3.0)
    cw = min(W, ch * OUT_W / CAM_H)
    ch = cw * CAM_H / OUT_W
    x = min(max(cx - cw / 2, 0), W - cw)
    y = min(max(cy - ch / 2, 0), H - ch)
    return {"mode": "stack", "cam": [round(x), round(y), round(cw), round(ch)], "cam_h": CAM_H,
            "W": W, "H": H}


def stack_from_box(box, cx, cy, W, H):
    """Crop exactly the facecam overlay. The top panel keeps the overlay's shape (600-960 px tall);
    if it is even wider/taller than that, trim the long side around the face."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    cam_h = _even(min(CAM_H_MAX, max(CAM_H_MIN, OUT_W * bh / bw)))
    a = OUT_W / cam_h                       # panel aspect w/h
    if bw / bh > a:                          # too wide: narrower window around the face
        cw, ch = bh * a, bh
        x, y = min(max(cx - cw / 2, x0), x1 - cw), y0
    else:                                    # too tall: shorter window around the face
        cw, ch = bw, bw / a
        x, y = x0, min(max(cy - ch / 2, y0), y1 - ch)
    return {"mode": "stack", "cam": [round(x), round(y), round(cw), round(ch)], "cam_h": cam_h,
            "W": W, "H": H}


def _edge(profile, lo, hi, ratio=EDGE_RATIO):
    """Index of the sharpest line in profile[lo:hi] if it stands out `ratio` x above the median."""
    lo, hi = max(0, int(lo)), min(len(profile), int(hi))
    if hi - lo < 2:
        return None
    seg = profile[lo:hi]
    i = max(range(len(seg)), key=seg.__getitem__)
    med = sorted(profile)[len(profile) // 2] or 1e-6
    return lo + i if seg[i] >= ratio * med else None


def cam_box_from_profiles(col, row, face, W, H):
    """Facecam overlay borders from edge profiles: col[x] = vertical-edge strength per column (rows
    around the face), row[y] = horizontal-edge strength per row (columns around the face). A side
    with no clear border falls back to the frame edge (overlay flush with it) or a face-sized margin."""
    fx, fy, fw, fh = face
    r = _edge(col, fx + fw + 5, fx + 6 * fw)
    left = _edge(col, fx - 4 * fw, fx - 5)
    b = _edge(row, fy + fh + 5, fy + 5 * fh)
    t = _edge(row, fy - 4 * fh, fy - 5)
    # no border found but the search reached the frame edge -> overlay is flush with it
    x0 = left if left is not None else (0 if fx - 4 * fw <= 0 else fx - 1.5 * fw)
    x1 = r if r is not None else (W if fx + 6 * fw >= W else fx + 2.5 * fw)
    y0 = t if t is not None else (0 if fy - 4 * fh <= 0 else fy - 1.5 * fh)
    y1 = b if b is not None else (H if fy + 5 * fh >= H else fy + 2.5 * fh)
    if r is None and left is None and b is None and t is None:
        return None
    return (int(x0), int(y0), int(x1), int(y1))


def dominant(faces, W):
    """The face seen most often: detections whose centres sit within CLUSTER*W of each other count
    as one face. Drops one-off hits (a face on a TV, a game character, a passer-by)."""
    if not faces:
        return []
    centres = [(x + w / 2, y + h / 2) for x, y, w, h in faces]

    def near(a, b):
        return abs(a[0] - b[0]) <= CLUSTER * W and abs(a[1] - b[1]) <= CLUSTER * W
    best = max(range(len(faces)), key=lambda i: sum(near(centres[i], c) for c in centres))
    return [f for f, c in zip(faces, centres) if near(centres[best], c)]


def _even(v):
    return int(v) // 2 * 2


def filtergraph(layout):
    """ffmpeg filter_complex prefix producing [v] at 1080x1920 from [0:v]."""
    W, H = layout["W"], layout["H"]
    if layout["mode"] == "stack":
        x, y, cw, ch = layout["cam"]
        cam_h = layout.get("cam_h", CAM_H)
        gh = OUT_H - cam_h
        gw = min(W, H * OUT_W / gh)           # gameplay: centre cut, panel aspect 1080:1152
        gx = (W - gw) / 2
        return (f"[0:v]split[c][g];"
                f"[c]crop={_even(cw)}:{_even(ch)}:{_even(x)}:{_even(y)},scale={OUT_W}:{cam_h},setsar=1[top];"
                f"[g]crop={_even(gw)}:{_even(min(H, gw * gh / OUT_W))}:{_even(gx)}:0,"
                f"scale={OUT_W}:{gh},setsar=1[bot];"
                f"[top][bot]vstack=inputs=2[v]")
    if not W or not H or layout.get("cx") is None:
        return f"[0:v]crop=w=min(iw\\,ih*{OUT_W}/{OUT_H}):h=ih,scale={OUT_W}:{OUT_H},setsar=1[v]"
    cw = min(W, H * OUT_W / OUT_H)
    x = min(max(layout["cx"] - cw / 2, 0), W - cw)
    return f"[0:v]crop={_even(cw)}:{_even(min(H, cw * OUT_H / OUT_W))}:{_even(x)}:0,scale={OUT_W}:{OUT_H},setsar=1[v]"


def caption_y(layout):
    """Where captions sit (ASS \\pos y, 1920 tall): on the seam for stack, a bit below centre for crop."""
    lay = layout or {}
    return lay.get("cam_h", CAM_H) if lay.get("mode") == "stack" else 1080


def sample_faces(video, start, end, samples=SAMPLES, model=None):
    """All face boxes (x, y, w, h, source pixels) found in `samples` frames between start and end."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    model = model or os.environ.get("CLIPPER_FACE_MODEL", MODEL)
    if not os.path.exists(model):
        return []
    import cv2  # lazy: optional dependency
    cap = cv2.VideoCapture(str(video))
    faces, det = [], None
    try:
        span = max(end - start, 0.1)
        for i in range(samples):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + span * (i + 0.5) / samples) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            sc = 640 / frame.shape[1]
            small = cv2.resize(frame, None, fx=sc, fy=sc)
            if det is None:
                det = cv2.FaceDetectorYN.create(model, "", (small.shape[1], small.shape[0]), 0.6)
            _, found = det.detect(small)
            for f in (found if found is not None else []):
                faces.append(tuple(int(v / sc) for v in f[:4]))
    finally:
        cap.release()
    return faces


def edge_profiles(video, start, end, face, samples=SAMPLES):
    """Mean |Sobel| per column (rows around the face) and per row (columns around the face)."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    import cv2
    import numpy as np
    fx, fy, fw, fh = face
    cap = cv2.VideoCapture(str(video))
    col = row = None
    try:
        span = max(end - start, 0.1)
        for i in range(samples):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + span * (i + 0.5) / samples) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
            H, W = g.shape
            gx = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3))
            gy = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
            c = gx[max(0, fy - fh):min(H, fy + 2 * fh)].mean(axis=0)
            r = gy[:, max(0, fx - fw):min(W, fx + 2 * fw)].mean(axis=1)
            col = c if col is None else col + c
            row = r if row is None else row + r
    finally:
        cap.release()
    return (None, None) if col is None else (col.tolist(), row.tolist())


def detect_layout(video, start, end):
    try:
        W, H = probe_size(video)
    except Exception:  # noqa: BLE001 - unreadable/odd file: let ffmpeg centre-crop with expressions
        return {"mode": "crop", "cx": None, "W": None, "H": None}
    try:
        faces = sample_faces(video, start, end)
    except Exception:  # noqa: BLE001 - no OpenCV / unreadable frames: centred crop
        faces = []
    lay = choose_layout(faces, W, H)
    if lay["mode"] == "stack":
        try:
            dom = dominant(faces, W)
            face = tuple(int(median(f[i] for f in dom)) for i in range(4))
            col, row = edge_profiles(video, start, end, face)
            box = cam_box_from_profiles(col, row, face, W, H) if col else None
            if box:
                lay = choose_layout(faces, W, H, cam_box=box)
        except Exception:  # noqa: BLE001 - keep the face-sized estimate
            pass
    return lay
