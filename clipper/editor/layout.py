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
CAM_H = 768                 # stack: facecam panel height (40 %), gameplay gets the rest
FACECAM_MAX_H = 0.20        # a face smaller than this (share of frame height) ...
FACECAM_EDGE = 0.34         # ... with its centre in the outer third -> corner facecam
SAMPLES = 8
CLUSTER = 0.08              # detections within 8 % of the frame width are the same face
MODEL = "/opt/clipper/models/face_detection_yunet_2023mar.onnx"


def probe_size(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def choose_layout(faces, W, H):
    """faces: [(x, y, w, h)] in source pixels from sampled frames (any number per frame)."""
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
    # facecam box: a few face-heights around the face, panel aspect 1080:768
    ch = min(H, fh * 3.0)
    cw = min(W, ch * OUT_W / CAM_H)
    ch = cw * CAM_H / OUT_W
    x = min(max(cx - cw / 2, 0), W - cw)
    y = min(max(cy - ch / 2, 0), H - ch)
    return {"mode": "stack", "cam": [round(x), round(y), round(cw), round(ch)], "W": W, "H": H,
            "face_w": round(fw)}


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
        gh = OUT_H - CAM_H
        gw = min(W, H * OUT_W / gh)           # gameplay: centre cut, panel aspect 1080:1152
        gx = (W - gw) / 2
        return (f"[0:v]split[c][g];"
                f"[c]crop={_even(cw)}:{_even(ch)}:{_even(x)}:{_even(y)},scale={OUT_W}:{CAM_H},setsar=1[top];"
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
    return CAM_H if (layout or {}).get("mode") == "stack" else 1080


def sample_faces(video, start, end, samples=SAMPLES, model=None):
    """All face boxes (x, y, w, h, source pixels) found in `samples` frames between start and end."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    import cv2  # lazy: optional dependency
    model = model or os.environ.get("CLIPPER_FACE_MODEL", MODEL)
    if not os.path.exists(model):
        return []
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


def detect_layout(video, start, end):
    try:
        W, H = probe_size(video)
    except Exception:  # noqa: BLE001 - unreadable/odd file: let ffmpeg centre-crop with expressions
        return {"mode": "crop", "cx": None, "W": None, "H": None}
    try:
        faces = sample_faces(video, start, end)
    except Exception:  # noqa: BLE001 - no OpenCV / unreadable frames: centred crop
        faces = []
    return choose_layout(faces, W, H)
