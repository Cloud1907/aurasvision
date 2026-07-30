"""Kamera keşfi ve akış adresi bulma — sahada "RTSP yolu neydi" turunu bitirir.

Üç yol, sırayla denenir:
  1. **ONVIF keşfi (WS-Discovery)** — ağdaki kameralar kendilerini duyurur. Kullanıcı
     hiçbir şey yazmadan liste gelir. Kameranın ONVIF'i kapalıysa görünmez.
  2. **ONVIF profil sorgusu** — IP + kullanıcı/şifre ile kameranın KENDİ bildirdiği
     ana akış ve substream adresleri alınır. En güvenilir yol; tahmin yok.
  3. **Marka şablonu / yol tarama** — ONVIF yoksa bilinen RTSP yolları denenir.
     Tahmine dayalı ama ONVIF'siz eski kameralarda tek seçenek.

Not: keşif yalnız YEREL ağı tarar (multicast); internete istek gitmez.
"""
from __future__ import annotations

from urllib.parse import quote, urlparse

# Marka bazlı RTSP yol şablonları — {ana, alt} akış.
# Kaynak: üreticilerin yayınladığı standart yollar; model bazında sapma olabilir,
# bu yüzden "dene ve doğrula" mantığıyla kullanılır (asla körlemesine kaydedilmez).
MARKA_YOLLARI: dict[str, list[tuple[str, str]]] = {
    "Hikvision":   [("/Streaming/Channels/101", "ana"), ("/Streaming/Channels/102", "alt")],
    "Dahua/Amcrest": [("/cam/realmonitor?channel=1&subtype=0", "ana"),
                      ("/cam/realmonitor?channel=1&subtype=1", "alt")],
    "Axis":        [("/axis-media/media.amp", "ana"),
                    ("/axis-media/media.amp?resolution=640x480", "alt")],
    "Reolink":     [("/h264Preview_01_main", "ana"), ("/h264Preview_01_sub", "alt")],
    "Uniview":     [("/media/video1", "ana"), ("/media/video2", "alt")],
    "TP-Link/Tapo": [("/stream1", "ana"), ("/stream2", "alt")],
    "Foscam":      [("/videoMain", "ana"), ("/videoSub", "alt")],
    "Bosch":       [("/rtsp_tunnel", "ana")],
    "Vivotek":     [("/live.sdp", "ana")],
    "Genel ONVIF": [("/onvif1", "ana"), ("/onvif2", "alt"), ("/live", "ana"), ("/11", "ana")],
}


def rtsp_kur(ip: str, yol: str, kullanici: str = "", sifre: str = "", port: int = 554) -> str:
    kimlik = f"{quote(kullanici, safe='')}:{quote(sifre, safe='')}@" if kullanici else ""
    return f"rtsp://{kimlik}{ip}:{port}{yol}"


def onvif_kesfet(sure: float = 4.0) -> list[dict]:
    """Yerel ağdaki ONVIF cihazlarını bulur → [{ip, xaddr, tipler}]."""
    from wsdiscovery.discovery import ThreadedWSDiscovery
    from wsdiscovery.scope import Scope

    wsd = ThreadedWSDiscovery()
    bulunan: list[dict] = []
    try:
        wsd.start()
        servisler = wsd.searchServices(
            scopes=[Scope("onvif://www.onvif.org/")], timeout=sure)
        gorulen: set[str] = set()
        for s in servisler:
            for x in s.getXAddrs():
                ip = urlparse(x).hostname or ""
                if not ip or ip in gorulen:
                    continue
                gorulen.add(ip)
                bulunan.append({"ip": ip, "xaddr": x,
                                "scopes": [str(sc) for sc in (s.getScopes() or [])][:6]})
    finally:
        try:
            wsd.stop()
        except Exception:
            pass
    return bulunan


def onvif_akislari(ip: str, kullanici: str, sifre: str, port: int = 80) -> dict:
    """Kameranın KENDİ bildirdiği akış adresleri — tahmin yok.

    Kurulu istemci ASENKRON (onvif-zeep-async); senkron uçtan çağrıldığı için
    kendi event loop'unda koşturulur.
    Döner: {ok, profiller:[{ad, cozunurluk, url}], ana, alt, hata}
    """
    import asyncio

    try:
        return asyncio.run(_onvif_async(ip, kullanici, sifre, port))
    except Exception as e:
        return {"ok": False, "hata": str(e)[:160]}


async def _onvif_async(ip: str, kullanici: str, sifre: str, port: int) -> dict:
    try:
        from onvif import ONVIFCamera
    except Exception as e:                       # kütüphane yoksa sessizce düş
        return {"ok": False, "hata": f"ONVIF kütüphanesi yok: {e}"}
    cam = None
    try:
        cam = ONVIFCamera(ip, port, kullanici, sifre)
        await cam.update_xaddrs()
        media = await cam.create_media_service()
        profiller = []
        for p in await media.GetProfiles():
            istek = media.create_type("GetStreamUri")
            istek.ProfileToken = p.token
            istek.StreamSetup = {"Stream": "RTP-Unicast",
                                 "Transport": {"Protocol": "RTSP"}}
            uri = (await media.GetStreamUri(istek)).Uri
            # Kamera kimlik bilgisini URI'ye koymaz; biz ekleriz
            if kullanici and "@" not in uri:
                uri = uri.replace("rtsp://", f"rtsp://{quote(kullanici, safe='')}:"
                                             f"{quote(sifre, safe='')}@", 1)
            vec = getattr(getattr(p, "VideoEncoderConfiguration", None), "Resolution", None)
            profiller.append({"ad": str(getattr(p, "Name", p.token)),
                              "cozunurluk": f"{vec.Width}x{vec.Height}" if vec else "?",
                              "piksel": (vec.Width * vec.Height) if vec else 0,
                              "url": uri})
        if not profiller:
            return {"ok": False, "hata": "Kamera profil bildirmedi"}
        sirali = sorted(profiller, key=lambda x: -x["piksel"])
        return {"ok": True, "profiller": profiller,
                "ana": sirali[0]["url"],
                "alt": sirali[-1]["url"] if len(sirali) > 1 else ""}
    except Exception as e:
        msg = str(e)
        if "401" in msg or "auth" in msg.lower():
            msg = "Kimlik doğrulama reddedildi — ONVIF kullanıcı/şifresi hatalı"
        elif "timed out" in msg.lower() or "refused" in msg.lower():
            msg = "Kameraya ulaşılamadı — IP/port doğru mu, ONVIF açık mı?"
        return {"ok": False, "hata": msg[:160]}
    finally:
        if cam is not None:
            try:
                await cam.close()
            except Exception:
                pass


def yol_dene(ip: str, kullanici: str, sifre: str, port: int = 554,
             marka: str = "", zaman_asimi: float = 6.0) -> list[dict]:
    """Bilinen RTSP yollarını dener, AÇILANLARI döndürür (tahmin değil, kanıt)."""
    import av

    adaylar: list[tuple[str, str, str]] = []
    for m, yollar in MARKA_YOLLARI.items():
        if marka and m != marka:
            continue
        for yol, tip in yollar:
            adaylar.append((m, yol, tip))

    calisan: list[dict] = []
    for m, yol, tip in adaylar:
        url = rtsp_kur(ip, yol, kullanici, sifre, port)
        try:
            with av.open(url, options={"rtsp_transport": "tcp", "stimeout": "4000000"},
                         timeout=zaman_asimi) as c:
                if not c.streams.video:
                    continue
                v = c.streams.video[0]
                calisan.append({"marka": m, "tip": tip, "url": url,
                                "cozunurluk": f"{v.width}x{v.height}",
                                "piksel": (v.width or 0) * (v.height or 0),
                                "codec": (v.codec_context.name or "").upper()})
        except Exception:
            continue
    return sorted(calisan, key=lambda x: -x["piksel"])
