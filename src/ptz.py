"""PTZ kontrolü (ONVIF) — pan/tilt/zoom komutları.

TRASSIR kıyasında kalan son büyük eksik. Tasarım kararları:
  - Bağlantı bilgisi kameranın RTSP kaynağından çıkarılır (rtsp://kullanici:sifre@ip)
    veya config.yaml kamera girdisindeki `onvif: {ip, port, user, password}` ile
    açıkça verilir (ONVIF portu RTSP'den farklıysa şart).
  - Yetenek sorgusu (destekliyor_mu) süreç ömrünce önbelleklenir: PTZ olmayan
    kameraya her panel açılışında SOAP atılmaz, UI pedi hiç göstermez.
  - Komut başına taze bağlantı kurulur (basit ve güvenli); gecikme sahada
    gerçek PTZ kamerayla ölçülüp gerekirse bağlantı havuzuna geçilir.

DONANIM NOTU: Elimizde PTZ kamera yokken yazıldı — akış "destek yok/ulaşılamadı"
hâllerinde sessizce kapanacak şekilde savunmacıdır; gerçek kamerayla ilk fırsatta
doğrulanmalı (bkz. bellek: kamera keşfi durumu).
"""
from __future__ import annotations

import asyncio
import threading
from urllib.parse import unquote, urlparse

# cid → {"destek": bool, "hata": str} — süreç ömrü önbelleği
_YETENEK: dict[str, dict] = {}
_KILIT = threading.Lock()


def baglanti_bilgisi(cam: dict) -> dict | None:
    """Kameradan ONVIF bağlantı dörtlüsünü çıkarır; çıkarılamıyorsa None."""
    o = cam.get("onvif") or {}
    if o.get("ip"):
        return {"ip": str(o["ip"]), "port": int(o.get("port", 80)),
                "user": str(o.get("user", "")), "password": str(o.get("password", ""))}
    u = urlparse(str(cam.get("source", "")))
    if u.scheme == "rtsp" and u.hostname:
        return {"ip": u.hostname, "port": int(o.get("port", 80)),
                "user": unquote(u.username or ""), "password": unquote(u.password or "")}
    return None   # dosya/HLS kaynağı — PTZ söz konusu değil


async def _ptz_ac(b: dict):
    """ONVIF bağlantısı + PTZ servisi + PTZ'li ilk profil token'ı."""
    from onvif import ONVIFCamera

    cam = ONVIFCamera(b["ip"], b["port"], b["user"], b["password"])
    await cam.update_xaddrs()
    media = await cam.create_media_service()
    profiller = await media.GetProfiles()
    token = next((p.token for p in profiller
                  if getattr(p, "PTZConfiguration", None) is not None), None)
    if token is None:
        await cam.close()
        return None, None, None
    ptz = await cam.create_ptz_service()
    return cam, ptz, token


def destekliyor_mu(cid: str, cam: dict) -> dict:
    """{destek, hata} — sonuç önbelleklenir (PTZ donanımı koşarken değişmez)."""
    with _KILIT:
        if cid in _YETENEK:
            return _YETENEK[cid]
    b = baglanti_bilgisi(cam)
    if b is None:
        sonuc = {"destek": False, "hata": "kaynak RTSP değil — PTZ yok"}
    else:
        async def _sor():
            c, ptz, token = await _ptz_ac(b)
            if c is None:
                return {"destek": False, "hata": "kamera PTZ profili bildirmedi"}
            await c.close()
            return {"destek": True, "hata": ""}
        try:
            sonuc = asyncio.run(asyncio.wait_for(_sor(), timeout=8))
        except Exception as e:
            sonuc = {"destek": False, "hata": str(e)[:120]}
    with _KILIT:
        _YETENEK[cid] = sonuc
    return sonuc


def yetenek_unut(cid: str) -> None:
    """Kamera silinince/değişince önbelleği düşür (server delete/patch çağırır)."""
    with _KILIT:
        _YETENEK.pop(cid, None)


def hareket(cam: dict, pan: float, tilt: float, zoom: float) -> None:
    """Sürekli hareket başlatır; dur() gelene dek sürer. Hızlar -1..1."""
    b = baglanti_bilgisi(cam)
    if b is None:
        raise ValueError("Kameranın ONVIF bağlantı bilgisi yok")
    kirp = lambda v: max(-1.0, min(1.0, float(v or 0)))

    async def _git():
        c, ptz, token = await _ptz_ac(b)
        if c is None:
            raise ValueError("Kamera PTZ profili bildirmedi")
        try:
            istek = ptz.create_type("ContinuousMove")
            istek.ProfileToken = token
            istek.Velocity = {"PanTilt": {"x": kirp(pan), "y": kirp(tilt)},
                              "Zoom": {"x": kirp(zoom)}}
            await ptz.ContinuousMove(istek)
        finally:
            await c.close()

    asyncio.run(asyncio.wait_for(_git(), timeout=8))


def dur(cam: dict) -> None:
    b = baglanti_bilgisi(cam)
    if b is None:
        return

    async def _dur():
        c, ptz, token = await _ptz_ac(b)
        if c is None:
            return
        try:
            await ptz.Stop({"ProfileToken": token, "PanTilt": True, "Zoom": True})
        finally:
            await c.close()

    asyncio.run(asyncio.wait_for(_dur(), timeout=8))
