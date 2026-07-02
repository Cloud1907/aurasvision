"""VideoAI web sunucusu — FastAPI.

Basit, kullanıcı-dostu yönetim arayüzü için backend:
  GET  /                     → web UI (web/index.html)
  GET  /api/cameras          → config'teki kameralar
  GET  /api/snapshot?camera= → kameradan anlık kare (JPEG; diske YAZILMAZ — KVKK)
  GET  /api/zones?camera=    → bölge/çizgi tanımları
  POST /api/zones            → bölge/çizgi kaydet (canvas editöründen)
  GET  /api/events?limit=    → birleşik olay akışı (count/plate/face)
  GET  /api/lists?kind=      → izleme listesi (plate | face)
  POST /api/lists            → listeye ekle
  DELETE /api/lists/{kind}/{id} → listeden sil

Çalıştırma: python -m src.server   (veya uvicorn src.server:app)
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
import uuid
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import load_config
from .store import Store

cfg = load_config()
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="AurasVision")


def _store() -> Store:
    return Store(cfg.get("paths.db_path", "output/videoai.db"))


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _cameras() -> list[dict]:
    base = list(cfg.get("cameras", []) or [])
    ids = {c.get("id") for c in base}
    s = _store()
    try:
        for c in s.list_cameras_db():
            if c["id"] not in ids:
                base.append(c)
    finally:
        s.close()
    return base


def _camera(camera_id: str) -> dict | None:
    return next((c for c in _cameras() if c.get("id") == camera_id), None)


@app.get("/api/cameras")
def api_cameras():
    return _cameras()


class CameraPayload(BaseModel):
    name: str
    source: str
    id: str = ""


def _slug(s: str) -> str:
    import re
    tr = str.maketrans("çğıiöşüÇĞIİÖŞÜ", "cgiiosucgiiosu")
    return re.sub(r"[^a-z0-9]+", "-", s.translate(tr).lower()).strip("-") or "kamera"


@app.post("/api/cameras")
def api_add_camera(p: CameraPayload):
    s = _store()
    try:
        cid = p.id or _slug(p.name)
        base = cid; i = 2
        existing = {c["id"] for c in _cameras()}
        while cid in existing:
            cid = f"{base}-{i}"; i += 1
        s.add_camera(cid, p.name, p.source, _now())
        return {"ok": True, "id": cid}
    finally:
        s.close()


@app.delete("/api/cameras/{cid}")
def api_del_camera(cid: str):
    s = _store()
    try:
        s.delete_camera(cid)
        return {"ok": True}
    finally:
        s.close()


# Snapshot TTL cache — VideoCapture pahalı; aynı kareyi N sn tekrar üretme (perf).
_SNAP_CACHE: dict[str, tuple[float, bytes]] = {}
_SNAP_TTL = 4.0  # saniye


def _grab_jpeg(source: str) -> bytes | None:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        return None
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total > 1:
        cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return buf.tobytes() if ok else None


@app.get("/api/snapshot")
def api_snapshot(camera: str = Query(...), fresh: int = 0):
    cam = _camera(camera)
    if not cam:
        raise HTTPException(404, "Kamera bulunamadı")
    now = time.time()
    cached = _SNAP_CACHE.get(camera)
    if not fresh and cached and now - cached[0] < _SNAP_TTL:
        data = cached[1]
    else:
        data = _grab_jpeg(cam["source"])
        if data is None:
            raise HTTPException(400, "Kare okunamadı")
        _SNAP_CACHE[camera] = (now, data)
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=4"})


class ZonePayload(BaseModel):
    camera: str
    zones: list[dict]   # [{kind, name, points:[[x,y]..], classes:[..], direction}]


@app.get("/api/zones")
def api_get_zones(camera: str = Query(...)):
    s = _store()
    try:
        return s.list_zones(camera)
    finally:
        s.close()


@app.post("/api/zones")
def api_save_zones(payload: ZonePayload):
    s = _store()
    try:
        s.clear_zones(payload.camera)   # editör tam durumu gönderir → değiştir
        for z in payload.zones:
            s.add_zone(payload.camera, z.get("kind", "line"), z.get("name", ""),
                       json.dumps(z.get("points", [])), json.dumps(z.get("classes", [])),
                       z.get("direction", ""), _now())
        return {"ok": True, "count": len(payload.zones)}
    finally:
        s.close()


def _saved_lines(camera_id: str) -> list[dict]:
    """Kameranın kayıtlı TÜM 'line' bölgelerini [{name,pts}] döndürür (çoklu çizgi)."""
    out: list[dict] = []
    s = _store()
    try:
        for z in s.list_zones(camera_id):
            if z["kind"] == "line":
                pts = json.loads(z["points"] or "[]")
                if len(pts) >= 2:
                    out.append({"name": z.get("name") or "Çizgi", "pts": [pts[0], pts[1]]})
    finally:
        s.close()
    return out


class RunPayload(BaseModel):
    camera: str
    kind: str = "count"   # count | plate | face | analyze


def _webify(video_rel: str) -> None:
    """OpenCV 'mp4v' çıktısını tarayıcı-uyumlu H.264'e çevirir (ffmpeg).

    Tarayıcılar mp4v (MPEG-4 Part 2) oynatmaz; H.264 (avc1) gerekir. ffmpeg kurulu.
    """
    import shutil
    import subprocess

    name = video_rel.rsplit("/", 1)[-1]
    path = ROOT / cfg.get("paths.output_dir", "output") / name
    if not path.exists():
        return
    ff = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    tmp = path.with_name(path.stem + "_web.mp4")
    try:
        subprocess.run([ff, "-y", "-i", str(path), "-c:v", "libx264", "-preset", "veryfast",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
                        "-loglevel", "error", str(tmp)], check=True, timeout=300)
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


JOBS: dict[str, dict] = {}
RUN_LOCK = threading.Lock()   # aynı anda tek analiz (SQLite yazma çakışmasını önler)


def _run_analysis(job_id: str, p: "RunPayload") -> None:
    job = JOBS[job_id]
    cam = _camera(p.camera)
    if not cam:
        job.update(status="error", error="Kamera bulunamadı"); return
    if not RUN_LOCK.acquire(blocking=False):
        job.update(stage="sırada bekliyor (başka analiz çalışıyor)")
        RUN_LOCK.acquire()
    source = cam["source"]; stem = Path(source).stem
    s = _store(); summary: dict = {}; videos: list[str] = []
    try:
        s.clear_analysis()  # her test koşusu temiz başlar (önceki olaylar/uyarılar silinir)
        if p.kind in ("count", "analyze"):
            job.update(stage="Sayım çalışıyor")
            from .count import run_count
            rid = s.start_run("count", source, _now(), "{}")
            res = run_count(source, cfg, save_video=True, store=s, run_id=rid,
                            lines=_saved_lines(p.camera) or None)
            summary["count"] = {"in": res.in_count, "out": res.out_count,
                                "frames": res.frames, "lines": res.lines}
            videos.append(f"/media/{stem}_count.mp4")
        if p.kind in ("plate", "analyze"):
            job.update(stage="Plaka çalışıyor")
            job["live"] = []   # okundukça canlı eklenir (UI aşağı akıtır)
            from .plate import run_plate
            rid = s.start_run("plate", source, _now(), "{}")
            res = run_plate(source, cfg, save_video=True, store=s, run_id=rid,
                            on_read=lambda pl, c, f, t: job["live"].append(
                                {"plate": pl, "conf": round(c, 2) if c else None, "frame": f, "ts": t}))
            voted = res.voted or [{"plate": x, "count": 1, "conf": None} for x in res.plates]
            plates = [v["plate"] for v in voted]
            matches = s.match_plates(plates)
            for m in matches:
                s.add_alert("plate", m["plate"], m["list_type"], m.get("label") or "", p.camera, _now())
            summary["plate"] = {"plates": plates, "total": res.total_reads,
                                "voted": voted, "alerts": matches}
            videos.append(f"/media/{stem}_plate.mp4")
        if p.kind in ("face", "analyze"):
            job.update(stage="Yüz çalışıyor")
            from .face import run_face
            watch = [{**w, "embedding": json.loads(w["embedding"])} for w in s.faces_with_embedding()]
            rid = s.start_run("face", source, _now(), "{}")
            res = run_face(source, cfg, save_video=True, store=s, run_id=rid, watch=watch)
            for m in res.matches:
                s.add_alert("face", m["name"], m["list_type"], m.get("label") or "", p.camera, _now())
            summary["face"] = {"detections": res.detections, "male": res.male, "female": res.female,
                               "avg_age": round(res.avg_age, 1), "alerts": res.matches}
            videos.append(f"/media/{stem}_face.mp4")
        job.update(stage="Video hazırlanıyor")
        for v in videos:
            _webify(v)
        job.update(status="done", stage="bitti", summary=summary, videos=videos)
    except Exception as e:  # job hatayı taşır, sunucu çökmez
        job.update(status="error", error=str(e))
    finally:
        s.close()
        RUN_LOCK.release()


@app.post("/api/run")
def api_run(p: RunPayload):
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "running", "stage": "başlıyor", "summary": {}, "videos": []}
    threading.Thread(target=_run_analysis, args=(job_id, p), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/run/{job_id}")
def api_run_status(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job bulunamadı")
    return {"job_id": job_id, **j}


@app.get("/api/events")
def api_events(limit: int = 50):
    s = _store()
    try:
        return s.recent_events(limit)
    finally:
        s.close()


@app.get("/api/alerts")
def api_alerts(limit: int = 20):
    s = _store()
    try:
        return s.recent_alerts(limit)
    finally:
        s.close()


class WatchPayload(BaseModel):
    kind: str           # plate | face
    value: str          # plaka metni veya kişi adı
    label: str = ""
    list_type: str = "blacklist"
    camera: str = ""    # face: bu kameranın karesinden embedding çıkar (enroll)


@app.get("/api/lists")
def api_lists(kind: str = Query("plate")):
    s = _store()
    try:
        return s.list_watch(kind)
    finally:
        s.close()


@app.post("/api/lists")
def api_add_watch(p: WatchPayload):
    s = _store()
    try:
        if p.kind == "plate":
            s.add_watch_plate(p.value, p.label, p.list_type, _now())
            return {"ok": True}
        # yüz: kamera verildiyse o kareden embedding çıkar (enroll)
        emb_json = None
        enrolled = False
        if p.camera:
            cam = _camera(p.camera)
            if cam:
                from .face import embed_largest_face
                emb = embed_largest_face(cam["source"], cfg)
                if emb is not None:
                    emb_json = json.dumps(emb); enrolled = True
        s.add_watch_face(p.value, p.label, p.list_type, _now(), embedding=emb_json)
        return {"ok": True, "enrolled": enrolled}
    finally:
        s.close()


@app.delete("/api/lists/{kind}/{row_id}")
def api_del_watch(kind: str, row_id: int):
    s = _store()
    try:
        s.delete_watch(kind, row_id)
        return {"ok": True}
    finally:
        s.close()


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

_OUT = ROOT / (cfg.get("paths.output_dir", "output"))
_OUT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=_OUT), name="media")


def main() -> None:
    import uvicorn

    host = cfg.get("server.host", "127.0.0.1")
    port = int(cfg.get("server.port", 8000))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
