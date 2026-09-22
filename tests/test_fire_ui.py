"""Yangın erken uyarısının operatör arayüzü sözleşmesi."""
from pathlib import Path
from datetime import datetime, timezone

from fastapi import HTTPException

from src import server
from src.config import Config


ROOT = Path(__file__).resolve().parent.parent


def test_events_api_fire_filtresini_kabul_eder(monkeypatch):
    """K17: Operatör yalnız yangın olaylarını API'den filtreleyebilmeli."""
    class Store:
        def recent_events(self, limit, tur, kamera):
            return [{"type": tur, "detail": "duman · on_uyari"}]

        def close(self):
            pass

    monkeypatch.setattr(server, "_store", lambda: Store())
    try:
        sonuc = server.api_events(limit=50, tur="fire", kamera="")
    except HTTPException as e:
        assert False, f"fire filtresi reddedildi: {e.detail}"
    assert sonuc[0]["type"] == "fire"


def test_bilinmeyen_bolge_turu_mevcut_cizimleri_silmeden_reddedilir(monkeypatch):
    """K21: Hatalı tür tam-durum kaydında mevcut bölgeleri silememeli."""
    class Store:
        cleared = False

        def clear_zones(self, _camera):
            self.cleared = True

        def add_zone(self, *_a, **_k):
            pass

        def close(self):
            pass

    store = Store()
    monkeypatch.setattr(server, "_store", lambda: store)
    payload = server.ZonePayload(camera="depo", zones=[{
        "kind": "bilinmeyen", "name": "x", "points": [[0, 0], [1, 0], [1, 1]]}])
    try:
        server.api_save_zones(payload)
    except HTTPException as e:
        assert e.status_code == 422
    else:
        assert False, "bilinmeyen bölge türü kabul edildi"
    assert store.cleared is False


def test_fire_testi_kuresel_pilot_kapisi_kapaliyken_baslamaz(monkeypatch):
    """K22: Tek-seferlik yangın testi de küresel rollout kapısını aşmamalı."""
    monkeypatch.setattr(server, "cfg", Config({"fire": {"enabled": False}}))
    try:
        server.api_run(server.RunPayload(camera="depo", kind="fire"))
    except HTTPException as e:
        assert e.status_code == 409
    else:
        assert False, "fire.enabled=false iken yangın testi başlatıldı"


def test_masaustu_yangin_gorevi_bolge_ve_alarm_dilini_tasir():
    """K18: Masaüstünde görev, izleme alanı, maske ve alarm ayrı görünmeli."""
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '["fire","Yangın"]' in html
    assert 'arac("fire","Yangın izleme"' in html
    assert 'arac("firemask","Yangın maskesi"' in html
    assert "fire_warning" in html


def test_mobil_yangin_alarmini_yuz_eslesmesi_diye_gostermez():
    """K19: Mobil alarm merkezi yangını kritik ve doğru adla göstermeli."""
    html = (ROOT / "web" / "mobil.html").read_text(encoding="utf-8")
    assert "fire_warning" in html
    assert "Yangın erken uyarısı" in html
    assert '["fire", "Yangın"]' in html


def test_olay_ozeti_toplam_ile_sayim_turunu_ayri_tutar(monkeypatch):
    """K29: Bir sayım olayı toplamı iki artırmamalı; pilot metriği bozulmamalı."""
    now = datetime.now(timezone.utc).isoformat()

    class Store:
        def recent_events(self, *_a, **_k):
            return [
                {"camera_id": "depo", "type": "count", "time": now},
                {"camera_id": "depo", "type": "plate", "time": now},
                {"camera_id": "depo", "type": "fire", "time": now},
            ]

        def recent_alerts(self, *_a, **_k):
            return []

        def close(self):
            pass

    monkeypatch.setattr(server, "_store", lambda: Store())
    sonuc = server.api_events_summary(hours=24)["cameras"][0]
    assert sonuc["count"] == 3
    assert sonuc["count_events"] == 1
    assert sonuc["plate"] == 1 and sonuc["fire"] == 1


def test_yangin_yetenegi_model_yokken_nedeniyle_kapali(monkeypatch):
    """K30: UI yalnız rollout bayrağını değil model hazır oluşunu da bilmeli."""
    monkeypatch.setattr(server, "cfg", Config({
        "fire": {"enabled": True, "model": "models/olmayan-fire.pt",
                 "engine": "rfdetr"}}))
    cap = server.api_capabilities()["fire"]
    assert cap["enabled"] is True
    assert cap["available"] is False
    assert "bulunamad" in cap["reason"].lower()


def test_yangin_yetenegi_motor_paketi_yokken_nedeniyle_kapali(monkeypatch, tmp_path):
    """K30: Ağırlık var diye çalışma-anı paketi yokluğu gizlenmemeli."""
    model = tmp_path / "fire.pt"
    model.write_bytes(b"test-weight")
    monkeypatch.setattr(server, "cfg", Config({
        "fire": {"enabled": True, "model": str(model), "engine": "rfdetr"}}))
    monkeypatch.setattr("src.dedektor.calisma_kapisi", lambda *_a, **_k: (_ for _ in ()).throw(
        ImportError("rfdetr paketi kurulu değil")))
    cap = server.api_capabilities()["fire"]
    assert cap["available"] is False
    assert "paketi kurulu değil" in cap["reason"]


def test_acik_yangin_gorevi_baska_gorev_duzenlemesini_kilitlemez(monkeypatch):
    """K36: Eksik model, mevcut fire=true kamerada diğer görevleri kilitlememeli."""
    camera = {"id": "depo", "name": "Depo", "source": "rtsp://kamera",
              "tasks": {"count": True, "fire": True}}

    class Store:
        saved = None

        def add_camera(self, *_a, **_k):
            pass

        def set_camera_tasks(self, _cid, tasks):
            self.saved = tasks

        def close(self):
            pass

    store = Store()
    monkeypatch.setattr(server, "_camera", lambda _cid: camera)
    monkeypatch.setattr(server, "_store", lambda: store)
    monkeypatch.setattr(server, "api_capabilities", lambda: {
        "fire": {"available": False, "reason": "model yok"}})
    sonuc = server.api_set_tasks(
        "depo", server.TasksPayload(tasks={"count": False, "fire": True}))
    assert sonuc["ok"] is True
    assert store.saved["count"] is False and store.saved["fire"] is True


def test_masaustu_yangin_kapisi_ve_409_hatasini_gorunur_kilar():
    """K31: Kullanıcı çalışmayan toggle değil, devre dışı nedenini görmeli."""
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'ctx.get("/capabilities")' in html  # ekran kapsamlı, iptal edilebilir GET
    assert "fireCap.available" in html
    assert "disabled" in html
    assert "Yangın görevi değiştirilemedi" in html
