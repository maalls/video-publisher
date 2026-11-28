#!/usr/bin/env python3
"""maskedit backend (v2): spaces > projects > clips > maskedit projects.

Listens on 127.0.0.1 only and trusts nobody directly: every request must carry the shared secret
(header X-Mk-Secret) and the list of spaces the signed-in user may use (header X-Mk-Spaces). The
editor's own login layer (a reverse proxy in front of this) checks the session, then adds both headers
and drops any copy sent by the browser.

Reads the editor's data folder (spaces/<space>/projects/<project>/project.json and media/) and stores
each maskedit project next to its clip:  <project>/maskedit/<clip asset>/<maskedit id>/doc.json (+ versions/).

Env: MASKEDIT_YABBE_DATA (data folder), MASKEDIT_SECRET_FILE, MASKEDIT_PORT (8796), MASKEDIT_PREFIX,
MASKEDIT_INGEST_PY + MASKEDIT_INGEST_CWD (python and folder used to add the exported mask as a project asset).
Needs OpenCV (cv2), numpy and ffmpeg.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import hmac, json, os, re, shutil, subprocess, sys, tempfile, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ["MASKEDIT_YABBE_DATA"])
SECRET = Path(os.environ["MASKEDIT_SECRET_FILE"]).read_text().strip()
PORT = int(os.environ.get("MASKEDIT_PORT", "8796"))
PREFIX = os.environ.get("MASKEDIT_PREFIX", "").rstrip("/")
INGEST_PY = os.environ.get("MASKEDIT_INGEST_PY")
INGEST_CWD = os.environ.get("MASKEDIT_INGEST_CWD")
WEB = HERE / "web"
ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_VERSIONS = 20
FRAME_MAX_W = 1100


class Err(Exception):
    def __init__(self, code, msg):
        self.code, self.msg = code, msg


def need_id(v):
    if not isinstance(v, str) or not ID.match(v):
        raise Err(400, "identifiant invalide")
    return v


# -- data access ---------------------------------------------------------------------

def space_names():
    try:
        return json.loads((DATA / "accounts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def project_dir(allowed, space, project):
    need_id(space); need_id(project)
    if space not in allowed:
        raise Err(403, "espace non autorisé")
    d = DATA / "spaces" / space / "projects" / project
    if not (d / "project.json").is_file():
        raise Err(404, "projet introuvable")
    return d


def load_project(d):
    return json.loads((d / "project.json").read_text(encoding="utf-8"))


def find_asset(d, clip):
    need_id(clip)
    for a in load_project(d).get("assets", []):
        if a.get("id") == clip and a.get("kind") == "video":
            f = d / "media" / a["filename"]
            if f.is_file():
                return a, f
    raise Err(404, "clip introuvable")


def mp_dir(d, clip, mp):
    need_id(clip); need_id(mp)
    return d / "maskedit" / clip / mp


def read_doc(md):
    try:
        return json.loads((md / "doc.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Err(404, "projet maskedit introuvable")


def write_doc(md, doc, snapshot=True):
    md.mkdir(parents=True, exist_ok=True)
    cur = md / "doc.json"
    if snapshot and cur.exists():
        vd = md / "versions"
        vd.mkdir(exist_ok=True)
        vs = sorted(vd.glob("*.json"))
        if not vs or time.time() - vs[-1].stat().st_mtime > 60:
            shutil.copyfile(cur, vd / (time.strftime("%Y%m%d-%H%M%S") + ".json"))
            for old in sorted(vd.glob("*.json"))[:-MAX_VERSIONS]:
                old.unlink()
    tmp = md / "doc.json.tmp"
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cur)


def summary(mp, doc):
    m = doc.get("meta", {})
    return {"id": mp, "name": m.get("name", mp), "status": m.get("status", "open"), "created": m.get("created"),
            "updated": m.get("updated"), "keyframes": len(doc.get("keyframes", [])), "rev": doc.get("rev", 0)}


# -- video frames --------------------------------------------------------------------

_readers = {}
_rlock = threading.Lock()


class Reader:
    def __init__(self, path):
        self.cap = cv2.VideoCapture(str(path))
        self.pos = 0
        self.lock = threading.Lock()
        self.used = time.time()

    def frame(self, n):
        with self.lock:
            self.used = time.time()
            if n != self.pos:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, n)
            ok, f = self.cap.read()
            self.pos = n + 1
        return f if ok else None


def reader(path):
    with _rlock:
        r = _readers.get(str(path))
        if r is None:
            if len(_readers) >= 4:
                old = min(_readers, key=lambda k: _readers[k].used)
                _readers.pop(old).cap.release()
            r = _readers[str(path)] = Reader(path)
        return r


CHUNK = 32
_cache = {}          # (path, chunk) -> list of jpeg bytes; insertion order = LRU order
_clock = threading.Lock()
_inflight = set()


def _enc(f, lw=0):
    h, w = f.shape[:2]
    mw = lw if lw else FRAME_MAX_W
    if w > mw:
        f = cv2.resize(f, (mw, round(h * mw / w)), interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 70 if lw else 75])[1].tobytes()


def _chunk(path, c, lw=0):
    """Decode one chunk of CHUNK frames sequentially (one seek at most), cache the JPEGs."""
    key = (str(path), c, lw)
    with _clock:
        v = _cache.get(key)
        if v is not None:
            _cache[key] = _cache.pop(key)
            return v
    r = reader(path)
    with r.lock:
        with _clock:
            v = _cache.get(key)
        if v is not None:
            return v
        r.used = time.time()
        if r.pos != c * CHUNK:
            r.cap.set(cv2.CAP_PROP_POS_FRAMES, c * CHUNK)
            r.pos = c * CHUNK
        out = []
        for _ in range(CHUNK):
            ok, f = r.cap.read()
            if not ok:
                break
            out.append(_enc(f, lw))
            r.pos += 1
    with _clock:
        _cache[key] = out
        mine = [k for k in _cache if bool(k[2]) == bool(lw)]
        while len(mine) > (90 if lw else 24):
            _cache.pop(mine.pop(0))
    return out


def _prefetch(path, c, lw=0):
    key = (str(path), c, lw)
    with _clock:
        if key in _cache or key in _inflight:
            return
        _inflight.add(key)
    def run():
        try:
            _chunk(path, c, lw)
        except Exception:
            pass
        finally:
            with _clock:
                _inflight.discard(key)
    threading.Thread(target=run, daemon=True).start()


PACK = 16


def proxy_pack(path, k, lw, pfps, fps, frames):
    """Interface proxy: frame i of the proxy is source frame int(i * fps / pfps + 0.5). Same wire format as frame_pack."""
    import struct
    n = int(-(-frames * pfps // fps))
    idx = [min(frames - 1, int(i * fps / pfps + 0.5)) for i in range(k * PACK, min(n, (k + 1) * PACK))]
    out = []
    for sfr in idx:
        ch = _chunk(path, sfr // CHUNK, lw)
        if sfr % CHUNK >= len(ch):
            break
        out.append(ch[sfr % CHUNK])
    if idx and idx[-1] // CHUNK + 1 < -(-frames // CHUNK):
        _prefetch(path, idx[-1] // CHUNK + 1, lw)
    if not out:
        return None
    return struct.pack("<I", len(out)) + b"".join(struct.pack("<I", len(x)) for x in out) + b"".join(out)


def frame_pack(path, k, lw=0):
    import struct
    c, i = divmod(k * PACK, CHUNK)
    ch = _chunk(path, c, lw)
    part = ch[i:i + PACK]
    if not part:
        return None
    if len(ch) == CHUNK and i + PACK >= CHUNK:
        _prefetch(path, c + 1, lw)
    return struct.pack("<I", len(part)) + b"".join(struct.pack("<I", len(x)) for x in part) + b"".join(part)


def frame_jpg(path, n):
    c, i = divmod(n, CHUNK)
    ch = _chunk(path, c)
    if i >= len(ch):
        return None
    if i >= CHUNK // 2 and len(ch) == CHUNK:
        _prefetch(path, c + 1)
    return ch[i]


def clip_info(path, a):
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or a.get("fps") or 30
    cap.release()
    return {"frames": n, "size": [w, h], "fps": round(float(fps), 3)}


# -- mask rendering / export ---------------------------------------------------------

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


def render_mask(doc, out_path, base_path=None):
    W, H = doc["size"]
    W, H = W - W % 2, H - H % 2
    base = cv2.VideoCapture(str(base_path)) if base_path else None
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                            "-r", str(doc["fps"]), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(out_path)],
                           stdin=subprocess.PIPE)
    for i in range(doc["frames"]):
        m = np.zeros((H, W), np.uint8)
        pts = points_at(doc, i)
        if len(pts) >= 3:
            cv2.fillPoly(m, [np.array([[p[0] * W, p[1] * H] for p in pts], np.int32)], 255)
        if base is not None:
            ok, f = base.read()
            if ok:
                g = f[:, :, 0] if f.ndim == 3 else f
                if g.shape != m.shape:
                    g = cv2.resize(g, (W, H), interpolation=cv2.INTER_NEAREST)
                m = np.maximum(m, (g > 127).astype(np.uint8) * 255)
        enc.stdin.write(m.tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise Err(500, "encodage du masque en échec")


# -- HTTP ----------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body=b"", ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode())

    def _auth(self):
        if not hmac.compare_digest(self.headers.get("X-Mk-Secret", ""), SECRET):
            raise Err(403, "accès refusé")
        return {s for s in self.headers.get("X-Mk-Spaces", "").split(",") if ID.match(s)}

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > 20_000_000:
            raise Err(413, "trop gros")
        return json.loads(self.rfile.read(n) or b"{}")

    def _route(self, method):
        allowed = self._auth()
        u = urlparse(self.path)
        p = u.path
        if PREFIX and p.startswith(PREFIX):
            p = p[len(PREFIX):]
        p = p or "/"
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if method == "GET":
            if p in ("/", "/index.html"):
                return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
            if p == "/app.js":
                return self._send(200, (WEB / "app.js").read_bytes(), "application/javascript")
            if p == "/api/spaces":
                names = space_names()
                return self._json([{"id": s, "name": names.get(s, s)} for s in sorted(allowed) if (DATA / "spaces" / s).is_dir()])
            if p == "/api/projects":
                sp = need_id(q.get("space", ""))
                if sp not in allowed:
                    raise Err(403, "espace non autorisé")
                out = []
                for pj in sorted((DATA / "spaces" / sp / "projects").glob("p_*/project.json")):
                    try:
                        j = json.loads(pj.read_text(encoding="utf-8"))
                        out.append({"id": j["id"], "name": j.get("name", j["id"]), "updated": j.get("updated_at", 0)})
                    except (OSError, ValueError, KeyError):
                        pass
                return self._json(sorted(out, key=lambda x: -x["updated"]))
            if p == "/api/clips":
                d = project_dir(allowed, q.get("space", ""), q.get("project", ""))
                out = [{"id": a["id"], "name": a.get("original_name", a["id"]), "duration": a.get("duration", 0),
                        "fps": a.get("fps", 0), "width": a.get("width", 0), "height": a.get("height", 0), "created": a.get("created_at", 0)}
                       for a in load_project(d).get("assets", [])
                       if a.get("kind") == "video" and a.get("status") == "ready" and not a.get("hidden") and a.get("has_video", True)]
                return self._json(sorted(out, key=lambda x: -x["created"]))
            if p == "/api/mprojects":
                d = project_dir(allowed, q.get("space", ""), q.get("project", ""))
                find_asset(d, q.get("clip", ""))
                base = d / "maskedit" / need_id(q.get("clip", ""))
                out = []
                for f in sorted(base.glob("*/doc.json")) if base.is_dir() else []:
                    try:
                        out.append(summary(f.parent.name, json.loads(f.read_text(encoding="utf-8"))))
                    except (OSError, ValueError):
                        pass
                return self._json(sorted(out, key=lambda x: -(x["updated"] or 0)))
            if p == "/api/doc":
                d = project_dir(allowed, q.get("space", ""), q.get("project", ""))
                find_asset(d, q.get("clip", ""))
                doc = read_doc(mp_dir(d, q["clip"], q.get("mp", "")))
                return self._json({"doc": doc, "rev": doc.get("rev", 0)})
            m = re.match(r"^/api/pack/([^/]+)/([^/]+)/([^/]+)/(\d+)\.bin$", p)
            if m:  # 16 consecutive frames in one response: [u32 count][u32 len]*count[jpeg bytes...]
                d = project_dir(allowed, m[1], m[2])
                a, f = find_asset(d, m[3])
                lw = int(q.get('w', '0') or 0)
                lw = lw if 160 <= lw <= 1920 else 0
                pf = float(q.get('pfps', '0') or 0)
                if pf > 0:
                    info = clip_info(f, a)
                    pf = min(pf, info["fps"])
                    b = proxy_pack(f, int(m[4]), lw, pf, info["fps"], info["frames"])
                else:
                    b = frame_pack(f, int(m[4]), lw)
                return self._send(200 if b else 404, b or b"", "application/octet-stream", {"Cache-Control": "private, max-age=3600"})
            m = re.match(r"^/api/frame/([^/]+)/([^/]+)/([^/]+)/(\d+)\.jpg$", p)
            if m:
                d = project_dir(allowed, m[1], m[2])
                _, f = find_asset(d, m[3])
                b = frame_jpg(f, int(m[4]))
                return self._send(200 if b else 404, b or b"", "image/jpeg", {"Cache-Control": "private, max-age=3600"})
            raise Err(404, "introuvable")
        body = self._body()
        d = project_dir(allowed, body.get("space", ""), body.get("project", ""))
        a, f = find_asset(d, body.get("clip", ""))
        if method == "POST" and p == "/api/mprojects":
            name = str(body.get("name", "")).strip()[:80] or "Sans titre"
            mp = "m_" + uuid.uuid4().hex[:10]
            info = clip_info(f, a)
            now = time.time()
            doc = {"version": 1, "clip": a["id"], **info, "keyframes": [], "mode": "replace", "base_mask": None, "rev": 1,
                   "meta": {"name": name, "status": "open", "created": now, "updated": now}}
            write_doc(mp_dir(d, a["id"], mp), doc, snapshot=False)
            return self._json({"id": mp, "doc": doc, "rev": 1}, 201)
        if method == "POST" and p == "/api/mproject-state":  # rename / close / reopen
            md = mp_dir(d, a["id"], body.get("mp", ""))
            doc = read_doc(md)
            if "name" in body:
                doc["meta"]["name"] = str(body["name"]).strip()[:80] or doc["meta"]["name"]
            if body.get("status") in ("open", "closed"):
                doc["meta"]["status"] = body["status"]
            doc["meta"]["updated"] = time.time()
            doc["rev"] = doc.get("rev", 0) + 1
            write_doc(md, doc)
            return self._json(summary(body["mp"], doc))
        if method == "PUT" and p == "/api/doc":
            md = mp_dir(d, a["id"], body.get("mp", ""))
            cur = read_doc(md)
            new = body.get("doc") or {}
            if new.get("version") != 1 or not isinstance(new.get("keyframes"), list):
                raise Err(400, "document invalide")
            if body.get("base_rev") != cur.get("rev", 0):
                raise Err(409, "le document a changé ailleurs (autre onglet)")
            for k in ("frames", "size", "fps", "clip", "meta"):  # fixed by the clip, not editable from the page
                new[k] = cur[k]
            if isinstance(new.get("proxy"), dict):  # interface proxy settings (per maskedit project)
                try:
                    new["proxy"] = {"fps": min(30, max(4, int(new["proxy"].get("fps", 12)))), "width": min(1920, max(320, int(new["proxy"].get("width", 960))))}
                except (TypeError, ValueError):
                    new.pop("proxy")
            else:
                new.pop("proxy", None)
            new["meta"]["updated"] = time.time()
            new["rev"] = cur.get("rev", 0) + 1
            write_doc(md, new)
            return self._json({"rev": new["rev"]})
        if method == "POST" and p == "/api/export":
            md = mp_dir(d, a["id"], body.get("mp", ""))
            doc = read_doc(md)
            if not INGEST_PY:
                raise Err(501, "ajout au projet non configuré")
            base_path = None
            if doc.get("base_mask") and doc.get("mode") == "union":
                _, base_path = find_asset(d, doc["base_mask"])
            tmpd = Path(tempfile.mkdtemp(prefix="maskedit-"))
            try:
                out = tmpd / "mask.mp4"
                render_mask(doc, out, base_path)
                name = "Masque maskedit - %s (%s).mp4" % (doc["meta"]["name"], datetime.now(ZoneInfo("Europe/Paris")).strftime("%d-%m-%Y %H:%M"))
                r = subprocess.run([INGEST_PY, str(HERE / "yabbe_ingest.py"), body["space"], body["project"], str(out), name],
                                   cwd=INGEST_CWD, capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    raise Err(500, "ajout au projet en échec: " + r.stderr[-300:])
                return self._json({"asset": r.stdout.strip().splitlines()[-1], "name": name})
            finally:
                shutil.rmtree(tmpd, ignore_errors=True)
        raise Err(404, "introuvable")

    def _run(self, method):
        try:
            self._route(method)
        except Err as e:
            self._json({"detail": e.msg}, e.code)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            print("error", repr(e), file=sys.stderr, flush=True)
            try:
                self._json({"detail": "erreur interne"}, 500)
            except Exception:  # noqa: BLE001
                pass

    def do_GET(self): self._run("GET")
    def do_POST(self): self._run("POST")
    def do_PUT(self): self._run("PUT")
    def log_message(self, *a): pass


if __name__ == "__main__":
    print("maskedit on 127.0.0.1:%d" % PORT, flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
