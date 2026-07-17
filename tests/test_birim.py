"""Birim testleri — saf fonksiyonlar ve store davranışları.

Çalıştırma: .venv/bin/python -m pytest tests/ -q
Model/GPU gerektirmez; ağır importlar (ultralytics, insightface) tetiklenmez.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bus import BusStore
from src.config import Config
from src.count import _ascii, _side
from src.face import (_affinity, _best_reid, _compact_gallery, _dedup_tracks,
                      _FaceTrack, _iou)
from src.plate import _as_float_conf, _lev, _vote
from src.server import _slug
from src.store import DEFAULT_TASKS, SqliteStore, merged_cameras


# ── Sayım: çizgi tarafı geometrisi ─────────────────────────────────
class TestCizgiGecisi:
    LINE = (0.5, 0.0, 0.5, 1.0)   # dikey orta çizgi (A→B yukarıdan bakışla sol→sağ)

    def test_soldan_saga_isaret_degisir(self):
        """Çizginin iki yanı zıt işaret üretmeli — geçiş tespitinin temeli."""
        sol = _side(0.2, 0.5, self.LINE)
        sag = _side(0.8, 0.5, self.LINE)
        assert sol * sag < 0

    def test_cizgi_ustu_sifir(self):
        assert _side(0.5, 0.3, self.LINE) == 0

    def test_yatay_cizgide_dikey_hareket(self):
        yatay = (0.0, 0.5, 1.0, 0.5)
        ust = _side(0.5, 0.2, yatay)
        alt = _side(0.5, 0.8, yatay)
        assert ust * alt < 0

    def test_ascii_turkce_karakter(self):
        assert _ascii("Giriş Çizgisi ÜĞİ") == "Giris Cizgisi UGI"


# ── Plaka: Levenshtein + çok-kareli oylama ─────────────────────────
class TestPlakaOylama:
    def test_lev_temel(self):
        assert _lev("34ABC123", "34ABC123") == 0
        assert _lev("34ABC123", "34A8C123") == 1   # B→8 OCR hatası
        assert _lev("", "ABC") == 3

    def test_ocr_varyantlari_tek_plakaya_iner(self):
        """Aynı aracın 5 gürültülü okuması tek plakada birleşmeli, en sık metin kazanmalı."""
        reads = [
            {"plate": "34ABC123", "confidence": 0.9, "frame_idx": 10, "ts_seconds": 1.0},
            {"plate": "34ABC123", "confidence": 0.8, "frame_idx": 12, "ts_seconds": 1.2},
            {"plate": "34A8C123", "confidence": 0.5, "frame_idx": 14, "ts_seconds": 1.4},
            {"plate": "34ABC128", "confidence": 0.4, "frame_idx": 16, "ts_seconds": 1.6},
            {"plate": "34ABC123", "confidence": 0.7, "frame_idx": 18, "ts_seconds": 1.8},
        ]
        voted = _vote(reads)
        assert len(voted) == 1
        assert voted[0]["plate"] == "34ABC123"
        assert voted[0]["count"] == 5

    def test_farkli_araclar_ayri_kalir(self):
        reads = [
            {"plate": "34ABC123", "confidence": 0.9, "frame_idx": 1, "ts_seconds": 0.1},
            {"plate": "06XYZ777", "confidence": 0.9, "frame_idx": 2, "ts_seconds": 0.2},
        ]
        assert len(_vote(reads)) == 2

    def test_conf_liste_ise_ortalama(self):
        assert _as_float_conf([0.8, 0.6]) == 0.7
        assert _as_float_conf(None) is None
        assert _as_float_conf(0.5) == 0.5


# ── Yüz: kutu benzerliği (IoU + merkez) ────────────────────────────
class TestYuzTakip:
    def test_ayni_kutu_iou_bir(self):
        b = (10, 10, 50, 50)
        assert _iou(b, b) == 1.0

    def test_ayrik_kutular_iou_sifir(self):
        assert _iou((0, 0, 10, 10), (100, 100, 110, 110)) == 0.0

    def test_kayan_yuz_affinity_yakalar(self):
        """IoU sıfır ama merkez yakın (kare atlama senaryosu) → affinity > 0 olmalı."""
        a = (100, 100, 140, 140)     # 40px yüz
        b = (145, 100, 185, 140)     # 45px sağa kaydı, örtüşme yok
        assert _iou(a, b) == 0.0
        assert _affinity(a, b) > 0.1

    def test_uzak_yuz_eslesmez(self):
        a = (100, 100, 140, 140)
        b = (400, 400, 440, 440)
        assert _affinity(a, b) == 0.0


# ── Yüz: embedding ile kimlik diriltme (re-id) ─────────────────────
class TestYuzReid:
    ESIK = 0.40   # config face.reid_threshold varsayılanı

    def _track(self, tid: int, emb) -> _FaceTrack:
        t = _FaceTrack(tid, (0.0, 0.0, 10.0, 10.0), 1, 0.0)
        t.emb = emb
        return t

    def test_esik_ustu_en_yakin_track_doner(self):
        """Yeni tespitin embedding'i gallery'deki aynı kişiye eşik üstü benziyorsa
        o track dirilmeli (yeni kişi sayılmamalı)."""
        ayni_kisi = self._track(1, [1.0, 0.0, 0.0])
        baska_kisi = self._track(2, [0.0, 1.0, 0.0])
        hit = _best_reid([0.95, 0.05, 0.0], [baska_kisi, ayni_kisi], self.ESIK)
        assert hit is ayni_kisi

    def test_esik_alti_none(self):
        """Benzerlik eşik altındaysa eşleşme yok → yeni track açılır."""
        g = [self._track(1, [1.0, 0.0, 0.0])]
        assert _best_reid([0.0, 1.0, 0.0], g, self.ESIK) is None
        # Embedding'i olmayan tespit / boş gallery de güvenle None döner
        assert _best_reid(None, g, self.ESIK) is None
        assert _best_reid([1.0, 0.0, 0.0], [], self.ESIK) is None


# ── Yüz: finalize öncesi embedding-dedup ───────────────────────────
class TestYuzDedup:
    ESIK = 0.40   # config face.reid_threshold varsayılanı

    def _track(self, tid: int, emb, n_frames: int = 10,
               ages=None, sexes=None, emb_score: float = 0.9) -> _FaceTrack:
        t = _FaceTrack(tid, (0.0, 0.0, 10.0, 10.0), tid, float(tid))
        t.emb = emb
        t.emb_score = emb_score if emb is not None else 0.0
        t.n_frames = n_frames
        t.ages = list(ages or [])
        t.sexes = list(sexes or [])
        return t

    def test_esik_ustu_birlesir(self):
        """Aynı kişinin iki track'i tek kümeye inmeli; temsilci n_frames büyük olan,
        demografi/kare sayısı birikmeli."""
        uzun = self._track(1, [1.0, 0.0, 0.0], n_frames=50, ages=[30], sexes=["M"])
        kisa = self._track(2, [0.95, 0.05, 0.0], n_frames=5, ages=[32], sexes=["M"])
        out = _dedup_tracks([kisa, uzun], self.ESIK)
        assert len(out) == 1
        c = out[0]
        assert c is uzun                      # büyük track küme temsilcisi
        assert c.n_frames == 55
        assert c.ages == [30, 32] and c.sexes == ["M", "M"]
        assert c.first_frame == 1 and c.first_ts == 1.0   # min alınır

    def test_esik_alti_birlesmez(self):
        a = self._track(1, [1.0, 0.0, 0.0])
        b = self._track(2, [0.0, 1.0, 0.0])
        assert len(_dedup_tracks([a, b], self.ESIK)) == 2

    def test_embsiz_aday_ayri_kume_kalir(self):
        """Embedding'i olmayan aday birleştirilemez — kendi kümesi olur."""
        a = self._track(1, [1.0, 0.0, 0.0], n_frames=50)
        b = self._track(2, None, n_frames=5)
        out = _dedup_tracks([a, b], self.ESIK)
        assert len(out) == 2 and b in out


# ── Yüz: gallery bellek sınırı (kompaktla + emekliye ayır) ─────────
class TestGalleryKompakt:
    ESIK = 0.40

    def _track(self, tid: int, emb, n_frames: int = 10) -> _FaceTrack:
        t = _FaceTrack(tid, (0.0, 0.0, 10.0, 10.0), tid, float(tid))
        t.emb = emb
        t.emb_score = 0.9 if emb is not None else 0.0
        t.n_frames = n_frames
        return t

    def test_sinir_altinda_dokunulmaz(self):
        g = [self._track(1, [1.0, 0.0, 0.0]), self._track(2, [0.0, 1.0, 0.0])]
        retired: list = []
        out = _compact_gallery(g, retired, 2, self.ESIK)
        assert out is g and retired == []

    def test_dedup_sinira_indirirse_emekli_yok(self):
        """Aynı kişinin iki girdisi birleşince sınır sağlanır → retired boş kalır."""
        g = [self._track(1, [1.0, 0.0, 0.0], 50),
             self._track(2, [0.95, 0.05, 0.0], 5),     # 1 ile aynı kişi
             self._track(3, [0.0, 1.0, 0.0], 20)]
        retired: list = []
        out = _compact_gallery(g, retired, 2, self.ESIK)
        assert len(out) == 2 and retired == []
        assert sum(t.n_frames for t in out) == 75   # 50+5 birleşti, 20 ayrı

    def test_fazlalik_en_dusuk_n_frames_emekliye(self):
        """Dedup yetmezse en az görülen track retired'a gider — final sayımda kalır."""
        g = [self._track(1, [1.0, 0.0, 0.0], 50),
             self._track(2, [0.0, 1.0, 0.0], 20),
             self._track(3, [0.0, 0.0, 1.0], 5)]        # üçü farklı kişi
        retired: list = []
        out = _compact_gallery(g, retired, 2, self.ESIK)
        assert len(out) == 2
        assert len(retired) == 1 and retired[0].tid == 3   # en düşük n_frames
        assert {t.tid for t in out} == {1, 2}


# ── Sunucu yardımcıları ────────────────────────────────────────────
class TestSlug:
    def test_turkce_ve_bosluk(self):
        assert _slug("Arka Kapı Girişi") == "arka-kapi-girisi"

    def test_bos_isim_varsayilan(self):
        assert _slug("!!!") == "kamera"


# ── Config ─────────────────────────────────────────────────────────
class TestConfig:
    def test_noktali_erisim_ve_varsayilan(self):
        c = Config({"a": {"b": {"c": 7}}})
        assert c.get("a.b.c") == 7
        assert c.get("a.x.y", "vars") == "vars"


# ── BusStore: olay sözleşmesi ──────────────────────────────────────
class SahteRedis:
    def __init__(self):
        self.mesajlar = []

    def xadd(self, stream, fields, **kw):
        self.mesajlar.append((stream, fields))


class TestBusStore:
    def test_count_olayi_yayinlanir(self):
        r = SahteRedis()
        BusStore(r).add_count_event("giris", 5, "in", "Kapı", 12.345, 310)
        stream, f = r.mesajlar[0]
        assert stream == "events" and f["type"] == "count" and f["camera_id"] == "giris"
        p = json.loads(f["payload"])
        assert p["direction"] == "in" and p["ts_seconds"] == 12.35 and p["frame_idx"] == 310

    def test_face_olayi_match_tasir(self):
        r = SahteRedis()
        BusStore(r).add_face_event("kasa", 30, "F", 0.9, 1.0, 10,
                                   track_id=3, match_name="Ali", match_score=0.7)
        p = json.loads(r.mesajlar[0][1]["payload"])
        assert p["match_name"] == "Ali" and p["track_id"] == 3


# ── SQLite store davranışları ──────────────────────────────────────
class TestSqliteStore:
    def _store(self, tmp_path):
        return SqliteStore(tmp_path / "t.db")

    def test_gorev_upsert_kamerayi_ezmez(self, tmp_path):
        """add_camera upsert'i mevcut görev anahtarlarını SİLMEMELİ (REPLACE tuzağı)."""
        s = self._store(tmp_path)
        s.add_camera("k1", "Kamera", "x.mp4")
        s.set_camera_tasks("k1", {"count": False, "plate": True, "face": False})
        s.add_camera("k1", "Kamera Yeni Ad", "y.mp4")   # upsert
        cams = s.list_cameras_db()
        assert cams[0]["name"] == "Kamera Yeni Ad"
        assert cams[0]["tasks"] == {"count": False, "plate": True, "face": False}
        s.close()

    def test_merged_cameras_db_gorevi_configi_ezer(self, tmp_path):
        s = self._store(tmp_path)
        cfg = Config({"cameras": [{"id": "giris", "name": "G", "source": "a.mp4",
                                   "tasks": {"count": True, "plate": False, "face": False}}]})
        s.add_camera("giris", "G", "a.mp4")
        s.set_camera_tasks("giris", {"count": True, "plate": True, "face": True})
        cams = merged_cameras(cfg, s)
        assert len(cams) == 1
        assert cams[0]["tasks"]["plate"] is True
        s.close()

    def test_merged_cameras_varsayilan_gorev(self, tmp_path):
        s = self._store(tmp_path)
        s.add_camera("yeni", "Y", "z.mp4")
        cams = merged_cameras(Config({}), s)
        assert cams[0]["tasks"] == DEFAULT_TASKS
        s.close()

    def test_health_son_durum(self, tmp_path):
        s = self._store(tmp_path)
        s.add_camera_health("k1", 5.0, 0, "ok")
        s.add_camera_health("k1", 4.0, 0, "error")
        s.commit()
        h = s.latest_health()
        assert len(h) == 1 and h[0]["status"] == "error"
        s.close()

    def test_izleme_listesi_normalize(self, tmp_path):
        s = self._store(tmp_path)
        s.add_watch_plate("34 abc 123", "e", "blacklist")
        assert s.match_plates(["34abc123"]) != []
        assert s.match_plates(["06XXX00"]) == []
        s.close()
