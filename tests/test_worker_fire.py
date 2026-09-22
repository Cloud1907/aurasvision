"""Yangın görevinin worker yaşam döngüsündeki güvenlik kapıları."""
from __future__ import annotations

import sys
import threading
from types import SimpleNamespace

import pytest

from src.config import Config
from src import worker
from src import gunluk


def _moduller(monkeypatch, *, count, fire):
    monkeypatch.setitem(sys.modules, "src.count", SimpleNamespace(run_count=count))
    monkeypatch.setitem(sys.modules, "src.fire", SimpleNamespace(run_fire=fire))


def test_etkin_gorevler_birbirini_bloklamadan_baslar(monkeypatch):
    """K13: Sürekli sayım akışı, aynı kameradaki yangın akışını aç bırakmamalı."""
    fire_started = threading.Event()

    def run_count(*_a, **_k):
        assert fire_started.wait(0.5), "yangın görevi sayım bitmeden başlamadı"

    def run_fire(*_a, **_k):
        fire_started.set()

    _moduller(monkeypatch, count=run_count, fire=run_fire)
    assert worker._gorevleri_kos(
        "depo", "rtsp://kamera", Config({"fire": {"enabled": True}}), object(),
        {"count": True, "fire": True}, None, [], [], []) is True


def test_bir_gorevin_hatasi_digerini_ac_birakmaz(monkeypatch):
    """K14/K26: Bir analiz çökerse bağımsız yangın görevi yine çalıştırılmalı."""
    calisan = []

    def run_count(*_a, **_k):
        raise RuntimeError("sayım modeli bozuk")

    def run_fire(*_a, **_k):
        calisan.append("fire")

    _moduller(monkeypatch, count=run_count, fire=run_fire)
    worker._gorevleri_kos(
        "depo", "rtsp://kamera",
        Config({"fire": {"enabled": True},
                "worker": {"task_max_restarts": 0}}), object(),
        {"count": True, "fire": True}, None, [], [], [])
    assert calisan == ["fire"]
    assert "count:parked" in worker._kamera_sagligi("depo")[1]


def test_coken_yangin_gorevi_kardes_calisirken_yeniden_baslar(monkeypatch):
    """K26: Sayım yaşarken çöken yangın thread'i bağımsız yeniden başlamalı."""
    ikinci_deneme = threading.Event()
    deneme = []

    def run_count(*_a, **_k):
        assert ikinci_deneme.wait(1.0), "yangın görevi yeniden başlamadı"

    def run_fire(*_a, **_k):
        deneme.append(1)
        if len(deneme) == 1:
            raise RuntimeError("geçici model hatası")
        ikinci_deneme.set()

    _moduller(monkeypatch, count=run_count, fire=run_fire)
    cfg = Config({"fire": {"enabled": True},
                  "worker": {"task_max_restarts": 2,
                             "task_retry_initial_seconds": 0}})
    assert worker._gorevleri_kos(
        "depo-retry", "rtsp://kamera", cfg, object(),
        {"count": True, "fire": True}, None, [], [], []) is True
    assert len(deneme) == 2
    assert "fire:done" in worker._kamera_sagligi("depo-retry")[1]


def test_supervisor_ustel_backoff_sonunda_park_eder(monkeypatch):
    """K26: Sürekli hata sınırsız hızlı döngü değil, backoff + parked üretmeli."""
    uykular = []

    def bozuk():
        raise RuntimeError("model açılamadı")

    sonuc = worker._gorev_gozetmeni(
        "depo-park", "fire", bozuk,
        Config({"worker": {"task_max_restarts": 2,
                            "task_retry_initial_seconds": 0.25,
                            "task_retry_max_seconds": 1.0}}),
        sleep_fn=uykular.append)
    assert sonuc == "parked"
    assert uykular == [0.25, 0.5]
    durum, detay = worker._kamera_sagligi("depo-park")
    assert durum == "error"
    assert "fire:parked" in detay


def test_supervisor_iptalde_yeniden_baslatmaz():
    """K26: Durdurma istendiğinde görev yeni kaynak açmadan çıkar."""
    dur = threading.Event()
    deneme = []

    def bozuk():
        deneme.append(1)
        raise RuntimeError("akış koptu")

    def bekle(_sure):
        dur.set()

    sonuc = worker._gorev_gozetmeni(
        "depo-stop", "fire", bozuk,
        Config({"worker": {"task_max_restarts": 5,
                            "task_retry_initial_seconds": 0.1}}),
        should_stop=dur.is_set, sleep_fn=bekle)
    assert sonuc == "stopped"
    assert len(deneme) == 1


def test_tum_gorevler_kapaninca_eski_parked_sagligi_temizlenir(monkeypatch):
    """K37: Görev kapatmak, önceki model hatasını heartbeat'te bırakmamalı."""
    worker._TASK_STAGE["depo-off"] = {"fire": "parked (model yok)"}
    assert worker._gorevleri_kos(
        "depo-off", "rtsp://kamera", Config({}), object(), {}, None, [], [], []) is False
    worker._STAGE["depo-off"] = "görev kapalı"
    assert worker._kamera_sagligi("depo-off") == ("ok", "görev kapalı")


def test_nvdec_kameralari_yangin_gorevine_gore_ayirir():
    """K27: Yangınlı kamera standart hatta, diğerleri NVDEC'de kalmalı."""
    cams = [
        {"id": "depo", "tasks": {"count": True, "fire": True}},
        {"id": "giris", "tasks": {"count": True, "fire": False}},
    ]
    nvdec, standart = worker._nvdec_kameralarini_ayir(cams)
    assert [c["id"] for c in nvdec] == ["giris"]
    assert [c["id"] for c in standart] == ["depo"]


def test_nvdec_yangin_gorevini_sessizce_yok_saymaz(monkeypatch):
    """K15/K27: NVDEC fire desteklemiyorsa kamera standart hatta çalışmalı."""
    cam = {"id": "depo", "source": "rtsp://kamera", "enabled": True,
           "tasks": {"fire": True}}

    class Store:
        def close(self):
            pass

    monkeypatch.setattr(worker, "load_config", lambda: Config({"worker": {"engine": "nvdec"},
                                                               "fire": {"enabled": True}}))
    monkeypatch.setattr(worker, "open_bus", lambda _cfg: object())
    monkeypatch.setattr(worker, "open_store", lambda _cfg: Store())
    monkeypatch.setattr(worker, "merged_cameras", lambda _cfg, _store: [cam])
    monkeypatch.setattr(worker, "_nvdec_kullanilabilir", lambda: "")
    monkeypatch.setattr(gunluk, "kur", lambda *_a, **_k: None)
    standart = []
    monkeypatch.setattr(worker, "_standart_workerlar", lambda cams, *_a, **_k: standart.extend(cams))
    monkeypatch.setitem(sys.modules, "src.gpu_engine",
                        SimpleNamespace(run_gpu_worker=lambda *_a, **_k: pytest.fail(
                            "yalnız yangın kamerası için NVDEC çağrılmamalı")))

    worker.main()
    assert [c["id"] for c in standart] == ["depo"]


def test_nvdec_calisirken_cokerse_yangin_kamerasini_ikinci_kez_acmaz(monkeypatch):
    """K32: Karma hatta NVDEC çöküşü, zaten açık yangın akışını çoğaltmamalı."""
    cams = [
        {"id": "depo", "source": "rtsp://depo", "enabled": True,
         "tasks": {"fire": True}},
        {"id": "giris", "source": "rtsp://giris", "enabled": True,
         "tasks": {"count": True}},
    ]

    class Store:
        def close(self):
            pass

    monkeypatch.setattr(worker, "load_config", lambda: Config({
        "worker": {"engine": "nvdec"}, "fire": {"enabled": True}}))
    monkeypatch.setattr(worker, "open_bus", lambda _cfg: object())
    monkeypatch.setattr(worker, "open_store", lambda _cfg: Store())
    monkeypatch.setattr(worker, "merged_cameras", lambda _cfg, _store: cams)
    monkeypatch.setattr(worker, "_nvdec_kullanilabilir", lambda: "")
    monkeypatch.setattr(gunluk, "kur", lambda *_a, **_k: None)
    acilan = []
    monkeypatch.setattr(
        worker, "_standart_workerlar",
        lambda secilen, *_a, **_k: acilan.extend(c["id"] for c in secilen))
    monkeypatch.setitem(sys.modules, "src.gpu_engine", SimpleNamespace(
        run_gpu_worker=lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("TensorRT çalışma anında çöktü"))))

    worker.main()
    assert sorted(acilan) == ["depo", "giris"]
