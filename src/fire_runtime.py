"""Yangın yetenek kontrolü ve tek-seferlik sunucu koşusunun küçük yardımcıları."""
from __future__ import annotations

from pathlib import Path


def capability(cfg, root: Path) -> dict:
    """Rollout, ağırlık, lisans ve motor paketini tek sonuçta doğrular."""
    etkin = bool(cfg.get("fire.enabled", False))
    motor = str(cfg.get("fire.engine", "rfdetr"))
    model = str(cfg.get("fire.model", "models/fire.pt"))
    model_path = Path(model)
    if not model_path.is_absolute():
        model_path = root / model_path
    neden = ""
    if not etkin:
        neden = "Yangın erken uyarısı pilot kapısı kapalı (fire.enabled=false)"
    elif not model_path.is_file():
        neden = f"Yangın modeli bulunamadı: {model}"
    else:
        try:
            from .dedektor import calisma_kapisi
            calisma_kapisi(motor, bool(cfg.get("fire.agpl_kabul", False)))
        except Exception as e:
            neden = str(e)
    return {"enabled": etkin, "available": not neden, "engine": motor,
            "model": model, "reason": neden}


def analyze_includes_fire(kind: str, fire_cap: dict) -> bool:
    """Açık fire isteğini korur; toplu analizde yalnız hazır yeteneği ekler."""
    return kind == "fire" or (kind == "analyze" and bool(fire_cap.get("available")))


def run_test(source: str, cfg, store, sandbox_store, camera_id: str,
             job: dict, push_frame) -> dict:
    """Kaydedilmiş bölgelerle tek-seferlik yangın analizini çalıştırır."""
    izleme, maske = [], []
    for zone in store.list_zones(camera_id):
        hedef = izleme if zone.get("kind") == "fire" else maske
        if zone.get("kind") in ("fire", "firemask"):
            hedef.append(zone)
    job["fire_live"] = {"on_uyari": [], "alarm": []}
    from .fire import run_fire
    store.start_run("fire", source)
    sonuc = run_fire(
        source, cfg, store=sandbox_store, camera_id=camera_id,
        bolgeler=izleme, maskeler=maske,
        on_event=lambda ev: job["fire_live"]["on_uyari"].append(dict(ev)),
        on_alert=lambda ev: job["fire_live"]["alarm"].append(dict(ev)),
        on_frame=push_frame, should_stop=job["cancel"].is_set)
    return {"frames": sonuc.frames, "on_uyari": len(sonuc.on_uyarilar),
            "alarm": len(sonuc.alarmlar)}
