#!/usr/bin/env python3
"""maskedit backend: serves the page, video frames, the JSON document, and exports the mask.

Binds to 127.0.0.1 only. No authentication here: put it behind a reverse proxy that
checks the user's login (that is the integration point). All URLs are relative, and an
optional path prefix (MASKEDIT_PREFIX, e.g. /lab/maskedit) is stripped from requests.

Env: MASKEDIT_SOURCE (video), MASKEDIT_BASE (optional base mask video, white = inside),
MASKEDIT_DOC (json path), MASKEDIT_OUT (export dir), MASKEDIT_PORT (default 8796).
Needs OpenCV (cv2), numpy and ffmpeg.
"""
import json, os, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = os.environ["MASKEDIT_SOURCE"]
BASE = os.environ.get("MASKEDIT_BASE") or None
DOC = Path(os.environ.get("MASKEDIT_DOC", HERE / "data" / "doc.json"))
OUT = Path(os.environ.get("MASKEDIT_OUT", HERE / "data" / "export"))
PORT = int(os.environ.get("MASKEDIT_PORT", "8796"))
PREFIX = os.environ.get("MASKEDIT_PREFIX", "").rstrip("/")
WEB = HERE / "web"
LOCK = threading.Lock()
_cap = cv2.VideoCapture(SOURCE)
W, H = int(_cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
FPS = _cap.get(cv2.CAP_PROP_FPS) or 16
N = int(os.environ.get("MASKEDIT_FRAMES", int(_cap.get(cv2.CAP_PROP_FRAME_COUNT))))


def frame_jpg(i):
    with LOCK:
        _cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(N - 1, i)))
        ok, f = _cap.read()
    if not ok:
        return None
    return cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()


def load_doc():
    if DOC.exists():
        return json.loads(DOC.read_text())
    return {"version": 1, "clip": Path(SOURCE).name, "fps": FPS, "size": [W, H], "frames": N,
            "keyframes": [], "mode": "union", "base_mask": Path(BASE).name if BASE else None}


def points_at(doc, frame):
    ks = sorted(doc["keyframes"], key=lambda k: k["frame"])
    if not ks:
        return []
    if frame <= ks[0]["frame"]:
        return ks[0]["points"]
    if frame >= ks[-1]["frame"]:
        return ks[-1]["points"]
    for a, b in zip(ks, ks[1:]):
        if a["frame"] <= frame <= b["frame"]:
            t = (frame - a["frame"]) / (b["frame"] - a["frame"])
            return [[p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t] for p, q in zip(a["points"], b["points"])]
    return []


def export(doc):
    OUT.mkdir(parents=True, exist_ok=True)
    name = "mask-%s.mp4" % Path(doc["clip"]).stem
    path = OUT / name
    base = cv2.VideoCapture(BASE) if BASE and doc.get("mode") == "union" else None
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)],
                           stdin=subprocess.PIPE)
    for i in range(doc["frames"]):
        m = np.zeros((H, W), np.uint8)
        pts = points_at(doc, i)
        if len(pts) >= 3:
            cv2.fillPoly(m, [np.array([[p[0] * W, p[1] * H] for p in pts], np.int32)], 255)
        if base is not None:
            ok, f = base.read()
            if ok:
                m = np.maximum(m, (f[:, :, 0] > 127).astype(np.uint8) * 255)
        enc.stdin.write(np.dstack([m] * 3).tobytes())
    enc.stdin.close()
    enc.wait()
    return str(path)


class H_(BaseHTTPRequestHandler):
    def _send(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _path(self):
        p = self.path.split("?")[0]
        if PREFIX and p.startswith(PREFIX):
            p = p[len(PREFIX):]
        return p or "/"

    def do_GET(self):
        p = self._path()
        if p in ("/", "/index.html"):
            return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
        if p == "/app.js":
            return self._send(200, (WEB / "app.js").read_bytes(), "application/javascript")
        if p.startswith("/frame/") and p.endswith(".jpg"):
            try:
                b = frame_jpg(int(p[7:-4]))
            except ValueError:
                b = None
            return self._send(200 if b else 404, b or b"", "image/jpeg")
        if p == "/api/doc":
            return self._send(200, json.dumps(load_doc()).encode())
        self._send(404, b"{}")

    def do_PUT(self):
        if self._path() != "/api/doc":
            return self._send(404, b"{}")
        doc = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if doc.get("version") != 1 or not isinstance(doc.get("keyframes"), list):
            return self._send(400, b'{"error":"bad document"}')
        DOC.parent.mkdir(parents=True, exist_ok=True)
        DOC.write_text(json.dumps(doc))
        self._send(200, b'{"ok":true}')

    def do_POST(self):
        if self._path() != "/api/export":
            return self._send(404, b"{}")
        doc = load_doc()
        self._send(200, json.dumps({"file": export(doc)}).encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("maskedit on 127.0.0.1:%d, %dx%d, %d frames" % (PORT, W, H, N), flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H_).serve_forever()
