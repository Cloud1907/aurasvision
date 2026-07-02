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

import os
import secrets
import threading
import time
import uuid
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import load_config
from .store import DEFAULT_TASKS, merged_cameras, open_store

cfg = load_config()
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="AurasVision")

# Erişim anahtarı: AURAS_TOKEN env set edilirse /api ve /media korunur.
# UI 401 alınca anahtar sorar (localStorage). Set edilmezse (yerel demo) auth kapalı.
API_TOKEN = os.environ.get("AURAS_TOKEN", "")


@app.middleware("http")
async def _auth(request: Request, call_next):
    p = request.url.path
    if API_TOKEN and (p.startswith("/api") or p.startswith("/media")):
        tok = request.headers.get("authorization", "")
        tok = tok[7:] if tok.lower().startswith("bearer ") else request.query_params.get("token", "")
        if not secrets.compare_digest(tok, API_TOKEN):
            return JSONResponse({"detail": "yetkisiz"}, status_code=401)
    return await call_next(request)


def _store():
    return open_store(cfg)


def _cameras() -> list[dict]:
    s = _store()
    try:
        return merged_cameras(cfg, s)
    finally:
        s.close()


def _sync_go2rtc() -> None:
    """Kameralardan go2rtc config'i üretir (canlı izleme fan-out'u).

    Kullanıcı go2rtc YAML'ı elle düzenlemez — kamera eklenince burada yenilenir.
    Dosya kaynakları ffmpeg: şemasıyla verilir (go2rtc döngüde oynatır).
    """
    rel = cfg.get("go2rtc.config_path", "")
    if not rel:
        return
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Otomatik üretilir (src/server.py) — kamera eklendikçe yenilenir.",
             "streams:"]
    for c in _cameras():
        src = str(c["source"])
        if not src.startswith(("rtsp://", "rtmp://", "http://", "https://")):
            # Dosya kaynağı → sonsuz döngülü RTSP (gerçek kamera simülasyonu).
            # compose ./data/videos'u konteynerde /data/videos'a mount eder.
            fpath = "/" + src.lstrip("/")
            src = (f"exec:ffmpeg -re -stream_loop -1 -i {fpath}"
                   " -c copy -f rtsp {output}")
        lines.append(f"  {c['id']}: {src}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
        s.add_camera(cid, p.name, p.source)
        _sync_go2rtc()
        return {"ok": True, "id": cid}
    finally:
        s.close()


@app.delete("/api/cameras/{cid}")
def api_del_camera(cid: str):
    s = _store()
    try:
        s.delete_camera(cid)
        _sync_go2rtc()
        return {"ok": True}
    finally:
        s.close()


class TasksPayload(BaseModel):
    tasks: dict


@app.post("/api/cameras/{cid}/tasks")
def api_set_tasks(cid: str, p: TasksPayload):
    cam = _camera(cid)
    if not cam:
        raise HTTPException(404, "Kamera bulunamadı")
    tasks = {k: bool(p.tasks.get(k, False)) for k in DEFAULT_TASKS}
    s = _store()
    try:
        # config kamerası DB'de yoksa önce upsert (görevler DB'de yaşar)
        s.add_camera(cid, cam["name"], cam["source"])
        s.set_camera_tasks(cid, tasks)
        return {"ok": True, "tasks": tasks}
    finally:
        s.close()


@app.get("/api/health")
def api_health():
    s = _store()
    try:
        return s.latest_health()
    finally:
        s.close()


@app.get("/api/sysinfo")
def api_sysinfo():
    return {"go2rtc": cfg.get("go2rtc.url", "")}


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
                       z.get("points", []), z.get("classes", []),
                       z.get("direction", "AtoB"))
        return {"ok": True, "count": len(payload.zones)}
    finally:
        s.close()


def _saved_lines(camera_id: str) -> list[dict]:
    """Kameranın kayıtlı TÜM 'line' bölgelerini [{name,pts,direction}] döndürür."""
    out: list[dict] = []
    s = _store()
    try:
        for z in s.list_zones(camera_id):
            if z["kind"] == "line":
                pts = z["points"] or []
                if len(pts) >= 2:
                    out.append({"name": z.get("name") or "Çizgi", "pts": [pts[0], pts[1]],
                                "direction": z.get("direction") or "AtoB"})
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
    s = None; summary: dict = {}; videos: list[str] = []
    try:
        # store açılışı da try içinde: hata olursa kilit finally'de MUTLAKA bırakılır
        s = _store()
        s.clear_analysis()  # her test koşusu temiz başlar (önceki olaylar/uyarılar silinir)
        if p.kind in ("count", "analyze"):
            job.update(stage="Sayım çalışıyor")
            from .count import run_count
            s.start_run("count", source)
            res = run_count(source, cfg, save_video=True, store=s, camera_id=p.camera,
                            lines=_saved_lines(p.camera) or None)
            summary["count"] = {"in": res.in_count, "out": res.out_count,
                                "frames": res.frames, "lines": res.lines}
            videos.append(f"/media/{stem}_count.mp4")
        if p.kind in ("plate", "analyze"):
            job.update(stage="Plaka çalışıyor")
            job["live"] = []   # okundukça canlı eklenir (UI aşağı akıtır)
            from .plate import run_plate
            s.start_run("plate", source)
            res = run_plate(source, cfg, save_video=True, store=s, camera_id=p.camera,
                            on_read=lambda pl, c, f, t: job["live"].append(
                                {"plate": pl, "conf": round(c, 2) if c else None, "frame": f, "ts": t}))
            voted = res.voted or [{"plate": x, "count": 1, "conf": None} for x in res.plates]
            plates = [v["plate"] for v in voted]
            matches = s.match_plates(plates)
            for m in matches:
                s.add_alert("plate", m["plate"], m["list_type"], m.get("label") or "", p.camera)
            summary["plate"] = {"plates": plates, "total": res.total_reads,
                                "voted": voted, "alerts": matches}
            videos.append(f"/media/{stem}_plate.mp4")
        if p.kind in ("face", "analyze"):
            job.update(stage="Yüz çalışıyor")
            from .face import run_face
            watch = s.faces_with_embedding()
            s.start_run("face", source)
            res = run_face(source, cfg, save_video=True, store=s, camera_id=p.camera, watch=watch)
            for m in res.matches:
                s.add_alert("face", m["name"], m["list_type"], m.get("label") or "", p.camera)
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
        if s is not None:
            s.close()
        RUN_LOCK.release()


@app.post("/api/run")
def api_run(p: RunPayload):
    job_id = uuid.uuid4().hex[:12]
    while len(JOBS) > 50:   # eski job kayıtları birikmesin
        JOBS.pop(next(iter(JOBS)))
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
            s.add_watch_plate(p.value, p.label, p.list_type)
            return {"ok": True}
        # yüz: kamera verildiyse o kareden embedding çıkar (enroll)
        emb = None
        if p.camera:
            cam = _camera(p.camera)
            if cam:
                from .face import embed_largest_face
                emb = embed_largest_face(cam["source"], cfg)
        s.add_watch_face(p.value, p.label, p.list_type, embedding=emb)
        return {"ok": True, "enrolled": emb is not None}
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

    _sync_go2rtc()
    host = cfg.get("server.host", "127.0.0.1")
    port = int(cfg.get("server.port", 8000))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
