"""Olay itme (webhook) — alarmları dış sisteme POST eder.

TRASSIR karşılaştırmasında saptanan eksik: dış sistemler bizden çekebiliyor
ama biz itemiyorduk. bildirim.webhook_url doluysa her alarm JSON olarak
oraya POST edilir (3 sn zaman aşımı, ayrı iş parçacığı — analiz hattını
ASLA bloklamaz, hata alarm yazımını engellemez).

Alıcı örneği: kurum santralı, Telegram köprüsü, SIEM, n8n/Zapier.
"""
from __future__ import annotations

import json
import threading
import urllib.request


def gonder(cfg, alarm: dict) -> None:
    url = (cfg.get("bildirim.webhook_url", "") or "").strip()
    if not url:
        return

    def _at() -> None:
        try:
            istek = urllib.request.Request(
                url, data=json.dumps(alarm, ensure_ascii=False, default=str).encode(),
                headers={"Content-Type": "application/json",
                         "User-Agent": "AurasVision"},
                method="POST")
            urllib.request.urlopen(istek, timeout=3).close()
        except Exception as e:
            # Alarm DB'ye yazıldı; webhook alıcısının çökmesi bizim kesintimiz
            # değildir — yalnız günlüğe düşer
            print(f"[bildirim] webhook iletilemedi: {e}", flush=True)

    threading.Thread(target=_at, daemon=True).start()
