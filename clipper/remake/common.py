"""Shared helpers for the remake engine (D58): paths, ffprobe, exact frame and audio decoding."""
import json
import os
import subprocess
from pathlib import Path

import numpy as np


def root():
    return Path(os.environ.get("CLIPPER_REMAKE", "/opt/clipper/remake"))


def fonts_dir():
    return os.environ.get("CLIPPER_FONTS", "/opt/clipper/fonts")


def ytdlp():
    return os.environ.get("YTDLP", "yt-dlp")


def workdir(short_id):
    d = root() / short_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(msg):
    print(f"[remake] {msg}", flush=True)


def probe(path):
    """{'w', 'h', 'fps', 'dur', 'audio'} of a media file."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
                         capture_output=True, check=True, text=True).stdout
    d = json.loads(out)
    v = next(s for s in d["streams"] if s.get("codec_type") == "video")
    num, den = v["r_frame_rate"].split("/")
    return {"w": int(v["width"]), "h": int(v["height"]), "fps": float(num) / float(den or 1),
            "dur": float(d["format"]["duration"]), "audio": any(s.get("codec_type") == "audio" for s in d["streams"])}


def seek(index, fps):
    """Input seek that lands exactly on frame `index` (half a frame early, then decode)."""
    return f"{max(0.0, (index - 0.5) / fps):.5f}"


def read_frames(path, first, count, fps, size, gray=False):
    """`count` frames from frame index `first`, scaled to size=(w, h). Fewer if the file ends."""
    w, h = size
    cmd = ["ffmpeg", "-v", "error", "-ss", seek(first, fps), "-i", str(path), "-frames:v", str(count),
           "-vf", f"scale={w}:{h}:flags=area", "-pix_fmt", "gray" if gray else "bgr24", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    c = 1 if gray else 3
    n = len(raw) // (w * h * c)
    a = np.frombuffer(raw[:n * w * h * c], np.uint8)
    return a.reshape(n, h, w) if gray else a.reshape(n, h, w, 3)


class FrameReader:
    """Frames of one file at native size, asked for in non-decreasing index order (one decoder per run)."""

    def __init__(self, path, fps, size):
        self.path, self.fps, (self.w, self.h) = path, fps, size
        self.proc, self.cur, self.buf = None, None, None

    def _start(self, index):
        self.close()
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", seek(index, self.fps), "-i", str(self.path),
                                      "-pix_fmt", "bgr24", "-f", "rawvideo", "-"],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.cur = index - 1

    def get(self, index):
        if self.proc is None or index < self.cur or index > self.cur + 120:
            self._start(index)
        n = self.w * self.h * 3
        while self.cur < index:
            b = self.proc.stdout.read(n)
            if len(b) < n:  # past the end: keep the last frame
                self.cur = index
                break
            self.buf = np.frombuffer(b, np.uint8).reshape(self.h, self.w, 3)
            self.cur += 1
        return self.buf

    def close(self):
        if self.proc is not None:
            self.proc.stdout.close()
            self.proc.kill()
            self.proc.wait()
            self.proc = None


def read_audio(path, sr, start=None, dur=None, highpass=None, stereo=False):
    """Float32 PCM (mono, or (n, 2) when stereo) from `start` for `dur` seconds."""
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{max(0.0, start):.5f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.5f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "2" if stereo else "1", "-ar", str(sr)]
    if highpass:
        cmd += ["-af", f"highpass=f={highpass}"]
    cmd += ["-f", "f32le", "-"]
    a = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32).copy()
    return a.reshape(-1, 2) if stereo else a


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=1, default=float))


def load_json(path):
    return json.loads(Path(path).read_text())
