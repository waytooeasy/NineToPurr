"""9:16 layout like the top clip channels (format research, 2026-10-19: NexxoRecaps, StreamBellz).

- "crop":  full-bleed 9:16 cut of the source that follows the people in it like a camera operator: both main
           faces when they fit, else the biggest, panning smoothly (IRL / just chatting). A static cut on the
           median face showed a white shirt and hands for most of Stable Ronaldo's fry clip (2026-10-21).
           A stream that burns its own captions at the bottom gets that band cut away (`cut`) so a moving cut
           never shows half a caption line; the Editor then draws ours, like the market's IRL Shorts.
- "chatstack": the same following crop on top and the stream's own chat overlay below it as a readable panel
           (Lucas 2026-10-21: "U can't even see the chat"; a 9:16 cut showed a cut-off strip of it). The chat
           box is found by Claude Haiku on two frames (both looks must agree); its spot in the picture is
           blurred so no half chat shows up there. No chat overlay -> plain crop.
- "stack": facecam on top, gameplay below, both full width (gaming with a corner facecam).
No blurred letterbox bars: none of the top channels use them. Black borders in the source itself (a stream's
black header bar, letterboxing) are measured (rows/columns that are near-black in every sampled frame, by
median, so a bar with a little text in it still counts) and kept out of every panel (`content`):
Jynxzi's black stats bar ran across the seam of a stack as a black band (2026-10-21).

`choose_layout()` is pure (tests need no OpenCV); `detect_layout()` samples frames with OpenCV's
YuNet face detector (model downloaded by setup.sh; OpenCV 5 dropped the Haar cascades).
No OpenCV, no model, no faces or any error -> centred crop.
"""
import json
import os
import re
import subprocess
from statistics import median

OUT_W, OUT_H = 1080, 1920
CAM_H = 768                 # stack: default facecam panel height (40 %), gameplay gets the rest
CAM_H_MIN, CAM_H_MAX = 600, 960   # a found facecam box keeps its own shape within these
EDGE_RATIO = 4.0            # an overlay border is a column/row this many times sharper than median
FACECAM_MAX_H = 0.20        # a face smaller than this (share of frame height) ...
FACECAM_EDGE = 0.34         # ... with its centre in the outer third -> corner facecam
MIN_CAM_W = 0.18            # a facecam panel cut from less than this share of the source width is blown up
                            # >3x and turns to mush (Lacy's 77x68 px cam bubble, 2026-10-20): full-bleed instead
FACECAM_MIN_H = 0.045       # a corner face smaller than this is a mini cam over an event/IRL broadcast
                            # (Adin's 33 px cam, 2026-10-19): blown up it is mush, so full-bleed the shot
SAMPLES = 8
TRACK_FPS = 2.0             # face samples per second for the moving crop
PAN_MAX = 0.25              # pan speed limit, share of the frame width per second
DEADBAND = 0.04             # target moves smaller than this share of the width don't move the camera
PAIR_FIT = 0.9              # two faces are framed together when they span <= 90 % of the crop width
MIN_FACE_SHARE = 0.35       # a face counts for framing when its area is >= 35 % of the frame's biggest
OWN_CAPTION_CUT = 0.14      # bottom share of the source cut when the stream burns its captions there
BORDER_MIN = 0.015          # a black border thinner than this share of the frame is left alone
CONTENT_MIN = 0.7           # never trim a side to less than 70 % (a dark scene can fool cropdetect)
BLACK = 24                  # a row/column whose median luma stays below this in every frame is border
SMALL_W, SMALL_H = 480, 270 # border search works on downscaled grey frames
CHAT_PANEL_MAX = 640        # chatstack: tallest chat panel (older lines above that are trimmed)
CHAT_PANEL_MIN = 140        # a thinner panel is unreadable: plain crop instead
CHAT_PAD = 0.015            # padding around the found chat box, share of the frame
CHAT_MAX_AREA = 0.35        # a "chat box" bigger than this share of the frame is a misread
CHAT_PROMPT = (
    "This is one frame of a livestream. Is a live chat overlay (usernames with their messages, often with badges or "
    "emotes, one per line) burned into the picture? Answer with JSON only: {\"chat\": true, \"box\": [x0, y0, x1, "
    "y1]} where the box covers ALL chat lines, as fractions of the image width and height (0-1), or {\"chat\": false}."
)
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
        return {"mode": "crop", "cx": cx, "W": W, "H": H, "follow": True}
    if fh < H * FACECAM_MIN_H:
        return {"mode": "crop", "cx": W / 2, "W": W, "H": H}
    if cam_box:
        lay = stack_from_box(cam_box, cx, cy, W, H)
        return lay if lay["cam"][2] >= MIN_CAM_W * W else {"mode": "crop", "cx": W / 2, "W": W, "H": H}
    # no borders found: a few face-heights around the face, panel aspect 1080:768
    ch = min(H, fh * 3.0)
    cw = min(W, ch * OUT_W / CAM_H)
    ch = cw * CAM_H / OUT_W
    if cw < MIN_CAM_W * W:
        return {"mode": "crop", "cx": W / 2, "W": W, "H": H}
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


def crop_w(W, H, cut=0.0, out_h=OUT_H):
    """Width of the window (source pixels) for an OUT_W x out_h panel over the kept height."""
    return min(W, H * (1 - cut) * OUT_W / out_h)


def target_cx(faces, cw):
    """Where the crop centre should be for one frame: the two main faces together when they fit in the
    window, else the biggest face. None when no face is seen."""
    if not faces:
        return None
    faces = sorted(faces, key=lambda f: -f[2] * f[3])
    top = faces[0][2] * faces[0][3]
    big = [f for f in faces if f[2] * f[3] >= MIN_FACE_SHARE * top][:2]
    if len(big) == 2:
        x0, x1 = min(f[0] for f in big), max(f[0] + f[2] for f in big)
        if x1 - x0 <= PAIR_FIT * cw:
            return (x0 + x1) / 2
    return big[0][0] + big[0][2] / 2


def smooth_path(points, W, cw, pan=PAN_MAX, dead=DEADBAND, lo=None, hi=None):
    """[(t, target or None)] -> camera path [(t, cx)]: gaps hold the last target, a median of 3 drops one-frame
    jumps, small moves inside the deadband are ignored (no jitter) and the pan speed is limited (no jump cuts).
    Clamped so the window stays inside the frame."""
    if not points:
        return []
    xs = [x for _, x in points]
    last = next((x for x in xs if x is not None), W / 2)
    filled = []
    for x in xs:
        last = x if x is not None else last
        filled.append(last)
    med = [median(filled[max(0, i - 1):i + 2]) for i in range(len(filled))]
    lo = cw / 2 if lo is None else lo
    hi = W - cw / 2 if hi is None else hi
    cur, prev_t, out = min(max(med[0], lo), hi), points[0][0], []
    for (t, _), x in zip(points, med):
        x = min(max(x, lo), hi)
        if abs(x - cur) > dead * W:
            step = pan * W * max(t - prev_t, 0)
            cur += max(-step, min(step, x - cur))
        out.append((t, cur))
        prev_t = t
    return out


def keyframes(path, eps=1.0):
    """Only the points where the camera changes speed (the rest are on straight lines between them)."""
    if len(path) <= 2:
        return list(path)
    keep = [path[0]]
    for a, b, c in zip(path, path[1:], path[2:]):
        s1 = (b[1] - a[1]) / max(b[0] - a[0], 1e-6)
        s2 = (c[1] - b[1]) / max(c[0] - b[0], 1e-6)
        if abs(s1 - s2) > eps:
            keep.append(b)
    keep.append(path[-1])
    return keep


def x_expr(path, cw, lo, hi):
    """ffmpeg crop x over time (t = seconds from the clip start), piecewise linear through the keyframes:
    x0 + sum(dx_i * clip((t - t_i) / dt_i, 0, 1)), kept within [lo, hi]. A flat sum, so long paths don't nest."""
    pts = [(t, cx - cw / 2) for t, cx in keyframes(path)]
    e = f"{pts[0][1]:.1f}"
    for (t0, x0), (t1, x1) in zip(pts, pts[1:]):
        if abs(x1 - x0) >= 0.5 and t1 > t0:
            e += f"{x1 - x0:+.1f}*clip((t-{t0:.2f})/{t1 - t0:.3f},0,1)"
    return f"clip({e},{lo:.0f},{hi:.0f})"


def fit_box(box, ox, oy, CW, CH):
    """A crop box (x, y, w, h) moved inside the content area; shrunk around its centre (same shape) if it
    is bigger than the content."""
    x, y, w, h = box
    k = min(1.0, CW / w if w else 1.0, CH / h if h else 1.0)
    cx, cy, w, h = x + w / 2, y + h / 2, w * k, h * k
    x = min(max(cx - w / 2, ox), ox + CW - w)
    y = min(max(cy - h / 2, oy), oy + CH - h)
    return x, y, w, h


def content(layout):
    """(x, y, w, h) of the picture inside the source's black borders, or the whole frame."""
    return tuple(layout.get("content") or (0, 0, layout["W"], layout["H"]))


def filtergraph(layout):
    """ffmpeg filter_complex prefix producing [v] at 1080x1920 from [0:v]."""
    W, H = layout["W"], layout["H"]
    if layout["mode"] == "stack":
        ox, oy, CW, CH = content(layout)
        x, y, cw, ch = fit_box(layout["cam"], ox, oy, CW, CH)
        cam_h = layout.get("cam_h", CAM_H)
        gh = OUT_H - cam_h
        gw = min(CW, CH * OUT_W / gh)         # gameplay: centre cut, panel aspect 1080:1152
        gx = ox + (CW - gw) / 2
        return (f"[0:v]split[c][g];"
                f"[c]crop={_even(cw)}:{_even(ch)}:{_even(x)}:{_even(y)},scale={OUT_W}:{cam_h},setsar=1[top];"
                f"[g]crop={_even(gw)}:{_even(min(CH, gw * gh / OUT_W))}:{_even(gx)}:{_even(oy)},"
                f"scale={OUT_W}:{gh},setsar=1[bot];"
                f"[top][bot]vstack=inputs=2[v]")
    if not W or not H or layout.get("cx") is None:
        return f"[0:v]crop=w=min(iw\\,ih*{OUT_W}/{OUT_H}):h=ih,scale={OUT_W}:{OUT_H},setsar=1[v]"
    cut = layout.get("cut") or 0.0
    chat = layout.get("chat") if layout["mode"] == "chatstack" else None
    ph = OUT_H - layout["chat_h"] if chat else OUT_H           # picture panel height
    ox, oy, CW, CH = content(layout)
    cw = crop_w(CW, CH, cut, ph)
    ch = min(CH * (1 - cut), cw * ph / OUT_W)
    if len(layout.get("path") or []) > 1:
        x = x_expr(layout["path"], cw, ox, ox + CW - cw).replace(",", "\\,")   # escaped like the fallback
    else:
        x = _even(min(max(layout["cx"] - cw / 2, ox), ox + CW - cw))
    y = _even(oy)
    if not chat:
        return f"[0:v]crop={_even(cw)}:{_even(ch)}:{x}:{y},scale={OUT_W}:{OUT_H},setsar=1[v]"
    x0, y0, x1, y1 = chat
    bw, bh = _even(x1 - x0), _even(y1 - y0)
    r = max(2, min(20, min(bw, bh) // 4))
    return (f"[0:v]split=3[s0][s1][s2];"
            f"[s1]crop={bw}:{bh}:{x0}:{y0},boxblur={r}:2[bl];"               # no half chat in the picture...
            f"color=c=black:s={bw}x{bh}:r=30:d=0.04,format=gray,geq=lum='{feather(chat, W, H)}',"
            f"loop=loop=-1:size=1[m];[bl][m]alphamerge[hide];"                # ...and no hard edge where it ends
            f"[s0][hide]overlay={x0}:{y0}:shortest=1[clean];"
            f"[clean]crop={_even(cw)}:{_even(ch)}:{x}:{y},scale={OUT_W}:{ph},setsar=1[pic];"
            f"[s2]crop={bw}:{bh}:{x0}:{y0},scale={OUT_W}:{layout['chat_h']},setsar=1[chat];"
            f"[pic][chat]vstack=inputs=2[v]")


def caption_y(layout):
    """Where captions sit (ASS \\pos y, 1920 tall): on the seam for stack, a bit below centre for crop."""
    lay = layout or {}
    return lay.get("cam_h", CAM_H) if lay.get("mode") == "stack" else 1080


def feather(box, W, H, f=40):
    """geq alpha for the blurred chat spot: opaque inside, fading out over `f` px on each side that borders the
    picture (a side on the frame edge needs no fade). Commas escaped for the filtergraph."""
    x0, y0, x1, y1 = box
    f = max(4, min(f, (x1 - x0) // 4, (y1 - y0) // 4))
    terms = [t for t, inner in (("X", x0 > 0), ("(W-1-X)", x1 < W), ("Y", y0 > 0), ("(H-1-Y)", y1 < H)) if inner]
    if not terms:
        return "255"
    e = f"{terms[0]}/{f}"
    for t in terms[1:]:
        e = f"min({e}\\,{t}/{f})"
    return f"255*clip({e}\\,0\\,1)"


def picture_bottom(layout):
    """Lowest y (output px) of the picture: above the chat panel in chatstack, else the frame bottom."""
    lay = layout or {}
    return OUT_H - lay["chat_h"] if lay.get("mode") == "chatstack" and lay.get("chat_h") else OUT_H


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


def track_faces(video, start, end, fps=TRACK_FPS, model=None):
    """[(t, faces)] every 1/fps s from start to end; t from the clip start, faces = [(x, y, w, h)] source px."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    model = model or os.environ.get("CLIPPER_FACE_MODEL", MODEL)
    if not os.path.exists(model):
        return []
    import cv2  # lazy: optional dependency
    cap = cv2.VideoCapture(str(video))
    out, det = [], None
    try:
        n = max(2, int((end - start) * fps) + 1)
        for i in range(n):
            t = min(end - start, i / fps)
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + t) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            sc = 640 / frame.shape[1]
            small = cv2.resize(frame, None, fx=sc, fy=sc)
            if det is None:
                det = cv2.FaceDetectorYN.create(model, "", (small.shape[1], small.shape[0]), 0.6)
            _, found = det.detect(small)
            out.append((t, [tuple(int(v / sc) for v in f[:4]) for f in (found if found is not None else [])]))
    finally:
        cap.release()
    return out


def _box(r):
    b = (r or {}).get("box")
    if not (isinstance(b, (list, tuple)) and len(b) == 4):
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in b)
    except (TypeError, ValueError):
        return None
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        return None
    return x0, y0, x1, y1


def chat_box_from_replies(replies, W, H):
    """Two independent looks -> one padded pixel box (x0, y0, x1, y1) when both see chat in about the same
    place (overlap >= 40 % of the union), else None. Boxes near a frame edge snap to it."""
    boxes = [_box(r) for r in replies if r and r.get("chat")]
    if len(replies) < 2 or len(boxes) < len(replies) or None in boxes:
        return None
    a, b = boxes[0], boxes[1]
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    u = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
    area_u = (u[2] - u[0]) * (u[3] - u[1])
    if area_u <= 0 or ix / area_u < 0.4:
        return None
    u = [max(0.0, u[0] - CHAT_PAD), max(0.0, u[1] - CHAT_PAD), min(1.0, u[2] + CHAT_PAD), min(1.0, u[3] + CHAT_PAD)]
    u = [0.0 if u[0] < 0.03 else u[0], 0.0 if u[1] < 0.03 else u[1],
         1.0 if u[2] > 0.97 else u[2], 1.0 if u[3] > 0.97 else u[3]]
    if (u[2] - u[0]) * (u[3] - u[1]) > CHAT_MAX_AREA or u[2] - u[0] > 0.5:
        return None
    return tuple(_even(round(v * s)) for v, s in zip(u, (W, H, W, H)))


def chat_layout(lay, box):
    """Crop layout -> chatstack: the picture on top, the chat box below at full width. A tall box keeps its
    newest (bottom) lines; a panel thinner than CHAT_PANEL_MIN is unreadable -> the plain crop stays."""
    if not box or lay.get("mode") != "crop":
        return lay
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    h = OUT_W * bh / bw
    if h > CHAT_PANEL_MAX:                      # keep the newest lines
        y0 = _even(round(y1 - bw * CHAT_PANEL_MAX / OUT_W))
        h = CHAT_PANEL_MAX
    if h < CHAT_PANEL_MIN:
        return lay
    return {**lay, "mode": "chatstack", "chat": [x0, y0, x1, y1], "chat_h": _even(h)}


def grab_frames(video, times, width=960):
    """JPEG bytes of the frames at `times` (s), scaled to `width`."""
    out = []
    for t in times:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                            "-vf", f"scale={width}:-2", "-f", "image2", "-c:v", "mjpeg", "-q:v", "3", "-"],
                           capture_output=True, check=True)
        out.append(r.stdout)
    return out


def find_chat(video, start, end, W, H, ask=None, grab=grab_frames):
    """The stream's chat overlay box (pixels) from two looks (Claude Haiku vision), or None. Never raises."""
    try:
        if ask is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                return None
            import visual_qa
            ask = lambda img: visual_qa.anthropic_vision([img], CHAT_PROMPT)  # noqa: E731
        span = max(end - start, 0.1)
        replies = []
        for img in grab(video, [start + span * 0.3, start + span * 0.7]):
            m = re.search(r"\{.*\}", ask(img) or "", re.S)
            replies.append(json.loads(m.group(0)) if m else None)
        return chat_box_from_replies(replies, W, H)
    except Exception:  # noqa: BLE001 - no chat panel is always fine
        return None


def follow(lay, video, start, end, track=track_faces):
    """Add the moving-camera path to a face crop (layout["path"] = [[t, cx], ...])."""
    if lay.get("mode") not in ("crop", "chatstack") or not lay.get("follow"):
        return lay
    ox, oy, CW, CH = content(lay)
    cw = crop_w(CW, CH, lay.get("cut") or 0.0, OUT_H - (lay.get("chat_h") or 0))
    pts = [(t, target_cx(f, cw)) for t, f in track(video, start, end)]
    if not any(x is not None for _, x in pts):
        return lay
    path = smooth_path(pts, lay["W"], cw, lo=ox + cw / 2, hi=ox + CW - cw / 2)
    return {**lay, "path": [[round(t, 2), round(x, 1)] for t, x in path]}


def grey_frames(video, times, w=SMALL_W, h=SMALL_H):
    """Downscaled grey frames (bytes, row-major w*h) at `times`."""
    out = []
    for t in times:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                            "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True)
        if len(r.stdout) == w * h:
            out.append(r.stdout)
    return out


def black_borders(frames, w, h, black=BLACK):
    """(x, y, w, h) in small-frame pixels of what is not near-black in every frame, or None (all black).
    Median per row/column: a black bar with a little text (viewer count, a chat line) stays a bar."""
    if not frames:
        return None
    rows = [max(median(f[y * w:(y + 1) * w]) for f in frames) for y in range(h)]
    cols = [max(median(f[y * w + x] for y in range(h)) for f in frames) for x in range(w)]
    ys = [y for y, v in enumerate(rows) if v >= black]
    xs = [x for x, v in enumerate(cols) if v >= black]
    if not ys or not xs:
        return None
    return xs[0], ys[0], xs[-1] - xs[0] + 1, ys[-1] - ys[0] + 1


def content_box(video, start, end, W, H, grab=grey_frames):
    """(x, y, w, h) in source pixels of the picture inside black borders (a stream's black header bar,
    letterboxing), from 3 frames of the window. None when there is nothing worth trimming or the result is
    implausible (a dark scene)."""
    try:
        span = max(end - start, 0.1)
        b = black_borders(grab(video, [start + span * f for f in (0.2, 0.5, 0.8)]), SMALL_W, SMALL_H)
    except Exception:  # noqa: BLE001 - no trimming is always fine
        return None
    if not b:
        return None
    sx, sy = W / SMALL_W, H / SMALL_H
    x0, y0 = _even(b[0] * sx), _even(b[1] * sy)
    x1, y1 = min(W, _even(round((b[0] + b[2]) * sx))), min(H, _even(round((b[1] + b[3]) * sy)))
    w, h = x1 - x0, y1 - y0
    if w < CONTENT_MIN * W or h < CONTENT_MIN * H:
        return None
    if max(x0, W - x1) < BORDER_MIN * W and max(y0, H - y1) < BORDER_MIN * H:
        return None
    return x0, y0, w, h


def detect_layout(video, start, end, cut=0.0):
    """`cut`: bottom share of the source to drop in crop mode (a stream's own burned-in caption band)."""
    try:
        W, H = probe_size(video)
    except Exception:  # noqa: BLE001 - unreadable/odd file: let ffmpeg centre-crop with expressions
        return {"mode": "crop", "cx": None, "W": None, "H": None}
    try:
        faces = sample_faces(video, start, end)
    except Exception:  # noqa: BLE001 - no OpenCV / unreadable frames: centred crop
        faces = []
    lay = choose_layout(faces, W, H)
    box = content_box(video, start, end, W, H)
    if box:
        lay["content"] = list(box)
    if lay["mode"] == "crop" and cut:
        lay["cut"] = cut
    if lay["mode"] == "crop" and lay.get("follow"):
        lay = chat_layout(lay, find_chat(video, start, end, W, H))
    try:
        lay = follow(lay, video, start, end)
    except Exception:  # noqa: BLE001 - keep the static face crop
        pass
    if lay["mode"] == "stack":
        try:
            dom = dominant(faces, W)
            face = tuple(int(median(f[i] for f in dom)) for i in range(4))
            col, row = edge_profiles(video, start, end, face)
            box = cam_box_from_profiles(col, row, face, W, H) if col else None
            if box:
                lay = {**choose_layout(faces, W, H, cam_box=box), **({"content": lay["content"]} if "content" in lay else {})}
        except Exception:  # noqa: BLE001 - keep the face-sized estimate
            pass
    return lay
