"""Birim testleri — saf fonksiyonlar ve store davranışları.

Çalıştırma: .venv/bin/python -m pytest tests/ -q
Model/GPU gerektirmez; ağır importlar (ultralytics, insightface) tetiklenmez.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bus import BusStore, YerelBus, publish
from src.config import Config
from src.count import _ascii, _side
from src.face import (_affinity, _best_reid, _calm_frac, _compact_gallery,
                      _dedup_tracks, _FaceTrack, _final_tracks, _iou,
                      _wander_ratio, run_face)
from src.plate import _as_float_conf, _lev, _vote, accept_read, normalize_tr
from src.server import _slug
from src.store import DEFAULT_TASKS, SqliteStore, merged_cameras
from src.zones import IntrusionWatcher, point_in_poly, wanted_classes


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


# ── İhlal alanı (poligon + bekleme + soğuma) ───────────────────────
class TestIhlalAlani:
    KARE = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]   # 100x100'de 20..80

    def _w(self, **kw):
        return IntrusionWatcher([{"name": "Depo", "points": self.KARE,
                                  "classes": kw.pop("classes", ["person"])}],
                                100, 100, kw.pop("dwell_seconds", 1.0),
                                kw.pop("cooldown_seconds", 5.0))

    def test_poligon_ici_disi(self):
        kare = [(0, 0), (100, 0), (100, 100), (0, 100)]
        assert point_in_poly(50, 50, kare) is True
        assert point_in_poly(150, 50, kare) is False
        assert point_in_poly(50, 50, [(0, 0), (10, 0)]) is False   # poligon değil

    def test_bekleme_dolmadan_alarm_yok(self):
        """Sınıra değip geçen nesne alarm üretmemeli (yanlış alarm filtresi)."""
        w = self._w()
        assert w.update([(1, 50, 50, 0)], 0.0) == []
        assert w.update([(1, 50, 50, 0)], 0.9) == []

    def test_bekleme_dolunca_alarm(self):
        w = self._w()
        w.update([(1, 50, 50, 0)], 0.0)
        al = w.update([(1, 50, 50, 0)], 1.5)
        assert len(al) == 1 and al[0]["zone"] == "Depo" and al[0]["track_id"] == 1

    def test_soguma_tekrar_alarmi_engeller(self):
        w = self._w()
        w.update([(1, 50, 50, 0)], 0.0)
        assert len(w.update([(1, 50, 50, 0)], 1.5)) == 1
        assert w.update([(1, 50, 50, 0)], 3.0) == []      # soğuma sürüyor
        assert len(w.update([(1, 50, 50, 0)], 7.0)) == 1  # soğuma bitti

    def test_alandan_cikinca_sayac_sifirlanir(self):
        """Girip çıkan nesne, toplam süresi eşiği aşsa bile alarm üretmemeli."""
        w = self._w()
        w.update([(1, 50, 50, 0)], 0.0)
        w.update([(1, 5, 5, 0)], 0.8)      # dışarı çıktı
        assert w.update([(1, 50, 50, 0)], 1.5) == []   # sayaç yeniden başladı

    def test_sinif_filtresi(self):
        """Yalnız 'insan' seçili alanda araç geçişi alarm üretmez."""
        w = self._w()
        w.update([(9, 50, 50, 2)], 0.0)
        assert w.update([(9, 50, 50, 2)], 2.0) == []

    def test_arac_secili_alanda_arac_yakalanir(self):
        w = self._w(classes=["car"])
        w.update([(9, 50, 50, 2)], 0.0)
        assert len(w.update([(9, 50, 50, 2)], 2.0)) == 1

    def test_sinif_secimi_yoksa_hepsi(self):
        w = self._w(classes=[])
        w.update([(9, 50, 50, 7)], 0.0)
        assert len(w.update([(9, 50, 50, 7)], 2.0)) == 1

    def test_gecersiz_poligon_atlanir(self):
        assert not IntrusionWatcher([{"name": "x", "points": [[0, 0], [1, 1]]}], 100, 100)

    def test_sinif_esleme(self):
        assert 0 in wanted_classes(["person"])
        assert 2 in wanted_classes(["car"]) and 7 in wanted_classes(["car"])
        assert wanted_classes([]) == set()


# ── Uyarı kabul akışı (denetim izi) ────────────────────────────────
class TestUyariKabul:
    def _store(self, tmp_path):
        return SqliteStore(str(tmp_path / "t.db"))

    def test_kabul_bekleyenlerden_duser_kayit_kalir(self, tmp_path):
        s = self._store(tmp_path)
        s.add_alert("plate", "34ABC123", "blacklist", "test", "kamera1")
        bekleyen = s.recent_alerts(10, pending_only=True)
        assert len(bekleyen) == 1
        assert s.ack_alert(bekleyen[0]["id"], "ayse") is True
        assert s.recent_alerts(10, pending_only=True) == []   # bekleyenden düştü
        hepsi = s.recent_alerts(10)
        assert len(hepsi) == 1 and hepsi[0]["acked_by"] == "ayse"   # kayıt SİLİNMEDİ
        s.close()

    def test_ayni_uyari_iki_kez_kabul_edilemez(self, tmp_path):
        s = self._store(tmp_path)
        s.add_alert("face", "Ali", "vip", "", "kamera1")
        aid = s.recent_alerts(10)[0]["id"]
        assert s.ack_alert(aid) is True
        assert s.ack_alert(aid) is False   # ikinci çağrı kimliği ezmez → API 404
        s.close()


# ── Plaka: TR format doğrulama + kabul kapısı ──────────────────────
class TestPlakaTRFormat:
    def test_gecerli_formatlar_aynen_gecer(self):
        for p in ("34A1234", "34AB123", "34AB1234", "06ABC12", "81ABC123"):
            assert normalize_tr(p) == p

    def test_rakam_pozisyonunda_harf_duzeltilir(self):
        assert normalize_tr("34ABC1Z3") == "34ABC123"   # Z→2
        assert normalize_tr("O6AB123") == "06AB123"     # O→0 (il kodu)
        assert normalize_tr("34AB12B") == "34AB128"     # B→8 (son blok)

    def test_harf_pozisyonunda_rakam_duzeltilir(self):
        assert normalize_tr("340B1234") == "34OB1234"   # 0→O (orta blok)

    def test_gecersiz_okumalar_reddedilir(self):
        assert normalize_tr("00AB123") is None    # il 00 yok
        assert normalize_tr("82AB123") is None    # il 82 yok
        assert normalize_tr("34QW123") is None    # W plakada kullanılmaz
        assert normalize_tr("ABC123") is None     # il kodu yok
        assert normalize_tr("34ABCD12") is None   # 4 harf olmaz
        assert normalize_tr("3") is None

    def test_kabul_kapisi_conf_none_bypass_edemez(self):
        """Güven skoru olmayan okuma eşiği atlayamaz (eski davranış açıktı)."""
        assert accept_read("34ABC123", None, 0.4) is None

    def test_kabul_kapisi_esik_ve_format(self):
        assert accept_read("34 ABC 123", 0.9, 0.4) == "34ABC123"
        assert accept_read("34ABC123", 0.3, 0.4) is None      # eşik altı
        assert accept_read("GARBAGE1", 0.9, 0.4) is None      # format dışı
        assert accept_read("GARBAGE1", 0.9, 0.4, fmt="none") == "GARBAGE1"


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
def _sahte_track(tid: int, embs, n_frames: int = 10,
                 ages=None, sexes=None, top_k: int = 3) -> _FaceTrack:
    """Test track'i: embs tek embedding, embedding listesi veya None olabilir."""
    t = _FaceTrack(tid, (0.0, 0.0, 10.0, 10.0), tid, float(tid))
    if embs is not None:
        if not isinstance(embs[0], (list, tuple)):
            embs = [embs]
        for i, e in enumerate(embs):
            t.add_emb(e, 0.9 - i * 0.1, tid, (0.0, 0.0, 10.0, 10.0), top_k)
    t.n_frames = n_frames
    t.ages = list(ages or [])
    t.sexes = list(sexes or [])
    return t


class TestYuzReid:
    ESIK = 0.30   # config face.reid_threshold varsayılanı

    def test_esik_ustu_en_yakin_track_doner(self):
        """Yeni tespitin embedding'i gallery'deki aynı kişiye eşik üstü benziyorsa
        o track dirilmeli (yeni kişi sayılmamalı)."""
        ayni_kisi = _sahte_track(1, [1.0, 0.0, 0.0])
        baska_kisi = _sahte_track(2, [0.0, 1.0, 0.0])
        hit = _best_reid([0.95, 0.05, 0.0], [baska_kisi, ayni_kisi], self.ESIK)
        assert hit is ayni_kisi

    def test_esik_alti_none(self):
        """Benzerlik eşik altındaysa eşleşme yok → yeni track açılır."""
        g = [_sahte_track(1, [1.0, 0.0, 0.0])]
        assert _best_reid([0.0, 1.0, 0.0], g, self.ESIK) is None
        # Embedding'i olmayan tespit / boş gallery de güvenle None döner
        assert _best_reid(None, g, self.ESIK) is None
        assert _best_reid([1.0, 0.0, 0.0], [], self.ESIK) is None

    def test_coklu_embedding_ikinci_pozdan_yakalar(self):
        """Track'in EN İYİ skorlu embedding'i uzak ama ikinci pozu yakınsa
        max-cosine yine eşleşmeli (tek temsilcinin kaçırdığı vaka)."""
        t = _sahte_track(1, [[1.0, 0.0, 0.0],      # en iyi skorlu poz (uzak)
                             [0.0, 1.0, 0.0]])     # ikinci poz (yakın)
        assert _best_reid([0.05, 0.95, 0.0], [t], self.ESIK) is t

    def test_top_k_en_iyi_skorlular_kalir(self):
        """add_emb yalnız en yüksek det_score'lu K embedding'i tutmalı."""
        t = _FaceTrack(1, (0.0, 0.0, 10.0, 10.0), 1, 0.0)
        for score, emb in [(0.5, [1.0, 0.0, 0.0]), (0.9, [0.0, 1.0, 0.0]),
                           (0.7, [0.0, 0.0, 1.0]), (0.6, [1.0, 1.0, 0.0])]:
            t.add_emb(emb, score, 1, (0.0, 0.0, 10.0, 10.0), 3)
        assert [e[0] for e in t.embs] == [0.9, 0.7, 0.6]   # 0.5 elendi, azalan sıralı


# ── Yüz: finalize öncesi embedding-dedup ───────────────────────────
class TestYuzDedup:
    ESIK = 0.30   # config face.reid_threshold varsayılanı

    def test_esik_ustu_birlesir(self):
        """Aynı kişinin iki track'i tek kümeye inmeli; temsilci n_frames büyük olan,
        demografi/kare sayısı birikmeli."""
        uzun = _sahte_track(1, [1.0, 0.0, 0.0], n_frames=50, ages=[30], sexes=["M"])
        kisa = _sahte_track(2, [0.95, 0.05, 0.0], n_frames=5, ages=[32], sexes=["M"])
        out = _dedup_tracks([kisa, uzun], self.ESIK)
        assert len(out) == 1
        c = out[0]
        assert c is uzun                      # büyük track küme temsilcisi
        assert c.n_frames == 55
        assert c.ages == [30, 32] and c.sexes == ["M", "M"]
        assert c.first_frame == 1 and c.first_ts == 1.0   # min alınır

    def test_esik_alti_birlesmez(self):
        a = _sahte_track(1, [1.0, 0.0, 0.0])
        b = _sahte_track(2, [0.0, 1.0, 0.0])
        assert len(_dedup_tracks([a, b], self.ESIK)) == 2

    def test_embsiz_aday_ayri_kume_kalir(self):
        """Embedding'i olmayan aday birleştirilemez — kendi kümesi olur."""
        a = _sahte_track(1, [1.0, 0.0, 0.0], n_frames=50)
        b = _sahte_track(2, None, n_frames=5)
        out = _dedup_tracks([a, b], self.ESIK)
        assert len(out) == 2 and b in out

    def test_coklu_embedding_birlesir_ve_top_k_korunur(self):
        """Kümeler embedding kümeleri üzerinden (max-max) birleşmeli; birleşen
        kümenin embedding sayısı top_k'yı aşmamalı."""
        a = _sahte_track(1, [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], n_frames=50)
        b = _sahte_track(2, [[0.0, 0.05, 0.99], [0.0, 1.0, 0.0]], n_frames=5)
        # temsilciler uzak (a0~b0 = 0) ama a1~b0 ≈ 0.99 → birleşmeli
        out = _dedup_tracks([a, b], self.ESIK, top_k=3)
        assert len(out) == 1
        assert len(out[0].embs) <= 3

    def test_es_zamanli_tracks_birlesmez(self):
        """Eş-zamanlılık vetosu: aynı işlenmiş karelerde İKİSİ DE tespit edilmiş
        iki track, embedding'leri NE KADAR benzer olursa olsun birleşmemeli —
        aynı anda görünen iki yüz iki ayrı insandır."""
        a = _sahte_track(1, [1.0, 0.0, 0.0], n_frames=50)
        b = _sahte_track(2, [0.99, 0.01, 0.0], n_frames=40)   # neredeyse özdeş emb
        a.seen = {100, 103, 106, 109, 112, 115}
        b.seen = {103, 106, 109, 112, 200, 203}               # 4 ortak tespit karesi
        out = _dedup_tracks([a, b], self.ESIK, top_k=3, co_overlap=2)
        assert len(out) == 2
        # Kontrol: aralıklar iç içe olsa da tespit SETLERİ ayrıksa (aynı kişinin
        # ardışık parçaları) birleşir; tespit seti birliği tutulur
        b.seen = {101, 104, 107, 110, 200, 203}
        out = _dedup_tracks([a, b], self.ESIK, top_k=3, co_overlap=2)
        assert len(out) == 1
        assert out[0] is a and {200, 203} <= out[0].seen and 101 in out[0].seen


# ── Yüz: doku filtreleri (donmuş gezinti + seken adım) ─────────────
CALM_EPS = 0.05   # config face.calm_step varsayılanı


def _konumlu_track(tid: int, centers, size: float = 20.0, emb=None,
                   n_frames: int = 10, match: str | None = None) -> _FaceTrack:
    """Merkezleri `centers` boyunca gezen test track'i (doku filtresi testleri).

    run_face akışıyla aynı: track ilk bbox ile açılır, her tespit karesinde
    mark_pos çağrılır (ilk çağrı adım saymaz). seen setleri tid bazlı ayrık →
    eş-zamanlılık vetosu devreye girmez, birleşme embedding benzerliğine kalır.
    """
    half = size / 2
    cx0, cy0 = centers[0]
    t = _FaceTrack(tid, (cx0 - half, cy0 - half, cx0 + half, cy0 + half),
                   tid * 1000, float(tid))
    for cx, cy in centers:
        bbox = (cx - half, cy - half, cx + half, cy + half)
        t.bbox = bbox
        t.mark_pos(bbox, CALM_EPS)
    if emb is not None:
        t.add_emb(emb, 0.9, tid * 1000, t.bbox, 3)
    t.n_frames = n_frames
    t.seen = set(range(tid * 1000, tid * 1000 + n_frames))
    t.match_name = match
    return t


class TestDokuFiltreleri:
    ESIK = 0.30       # config face.reid_threshold varsayılanı
    MIN_MOVE = 0.05   # config face.min_track_move varsayılanı
    MIN_CALM = 0.30   # config face.min_calm_frac varsayılanı

    def _final(self, cands):
        return _final_tracks(cands, self.ESIK, 3, 2, self.MIN_MOVE, self.MIN_CALM)

    def test_gezinti_orani(self):
        """Oran = merkezin max eksen aralığı / son yüz boyutu (uzun kenar)."""
        sabit = _konumlu_track(1, [(100, 100)] * 5)
        assert _wander_ratio(sabit) == 0.0
        gezen = _konumlu_track(2, [(100, 100), (110, 100)], size=20.0)
        assert abs(_wander_ratio(gezen) - 0.5) < 1e-9   # 10 px / 20 px

    def test_donmus_doku_elenir_sakin_gezinen_yuz_kalir(self):
        """Kaldırım taşı/duvar deseni yerinden oynamaz → donmuş doku, elenmeli;
        küçük sakin adımlarla ilerleyen gerçek yüz kalmalı."""
        doku = _konumlu_track(1, [(300, 300)] * 8, emb=[1.0, 0.0, 0.0])
        # adım 0.6 px = 0.03 × boyut (sakin), toplam gezinti 4.2 px = 0.21 × boyut
        yuz = _konumlu_track(2, [(100 + 0.6 * i, 100) for i in range(8)],
                             emb=[0.0, 1.0, 0.0])
        assert self._final([doku, yuz]) == [yuz]

    def test_seken_doku_elenir(self):
        """Abide vakası: tespit taştan taşa sıçrar → gezinti büyük ama hiçbir
        adım sakin değil → seken doku, elenmeli."""
        t = _konumlu_track(1, [(100 + 8 * i, 100) for i in range(8)],
                           emb=[1.0, 0.0, 0.0])   # adım 8 px = 0.4 × boyut
        assert _wander_ratio(t) > self.MIN_MOVE   # gezinti filtresi tek başına kör
        assert self._final([t]) == []

    def test_matchli_doku_benzeri_track_kalir(self):
        """İzleme eşleşmeli track donmuş da olsa KALIR — ArcFace eşleşmesi
        dokudan gelmez, elemek eşleşme olayını kaybettirir."""
        t = _konumlu_track(1, [(300, 300)] * 8, emb=[1.0, 0.0, 0.0], match="ali")
        assert self._final([t]) == [t]

    def test_esik_sinirlari_kalir(self):
        """Gezinti tam min_move'a, sakin oranı tam min_calm'a eşitse eleme YOK
        (yalnız eşik 'altında' elenir)."""
        # İki sakin adımla (0.5 px + 0.7 px) toplam gezinti tam 1 px = 0.05 × boyut
        t = _konumlu_track(1, [(100, 100), (100.5, 100), (101, 100.5)], size=20.0)
        assert abs(_wander_ratio(t) - self.MIN_MOVE) < 1e-9
        assert _calm_frac(t) >= self.MIN_CALM
        assert self._final([t]) == [t]

    def test_eleme_dedup_oncesi_benzer_dokular_kurtulamaz(self):
        """Eleme TRACK bazında ve dedup'tan ÖNCE: farklı konumlardaki iki donmuş
        doku parçasının embedding'leri benzese de, dedup birleşmesinin şişirdiği
        küme gezintisi onları KURTARMAMALI (abide ölçümü: doku kümeleri 5-58x
        gezinti gösterip küme-bazlı elemeden kaçıyordu)."""
        a = _konumlu_track(1, [(100, 100)] * 5, emb=[1.0, 0.0, 0.0], n_frames=20)
        b = _konumlu_track(2, [(160, 100)] * 5, emb=[0.99, 0.01, 0.0], n_frames=5)
        assert self._final([a, b]) == []

    def test_gezinen_parcalar_dedupta_birlesir_sayaclar_birikir(self):
        """Sakin adımlarla gezinen iki parça elemeden geçip dedup'ta birleşmeli;
        birleşen kümenin gezinti aralığı iki parçayı da kapsamalı, adım
        sayaçları birikmeli."""
        a = _konumlu_track(1, [(100 + 0.6 * i, 100) for i in range(8)],
                           emb=[1.0, 0.0, 0.0], n_frames=20)
        b = _konumlu_track(2, [(200 + 0.6 * i, 100) for i in range(8)],
                           emb=[0.99, 0.01, 0.0], n_frames=5)
        out = self._final([a, b])
        assert len(out) == 1 and out[0] is a
        assert out[0].cx_min == 100.0 and abs(out[0].cx_max - 204.2) < 1e-9
        assert out[0].n_steps == 14 and out[0].n_calm == 14


# ── Yüz: det_min_score skor tabanı (run_face, GPU'suz stub'larla) ──
class _SahteYuz:
    """InsightFace Face nesnesi taklidi — run_face'in okuduğu alanlar."""

    def __init__(self, bbox, score: float, emb):
        self.bbox = list(bbox)
        self.det_score = score
        self.age = 30
        self.sex = "M"
        self.normed_embedding = emb


class _SahteApp:
    """FaceAnalysis taklidi: kare sırasına göre önceden kurgulanmış tespit listeleri."""

    def __init__(self, frames_faces):
        self._ff = frames_faces
        self._i = 0

    def get(self, frame):
        i, self._i = self._i, self._i + 1
        return self._ff[i] if i < len(self._ff) else []


class _SahteCap:
    """cv2.VideoCapture taklidi: n kare 'okur', kare içeriği kullanılmaz."""

    def __init__(self, n: int):
        self._n = n
        self._i = 0

    def isOpened(self):
        return True

    def get(self, prop):
        return 25.0   # FPS; genişlik/yükseklik save_video=False'ta okunmaz

    def read(self):
        if self._i >= self._n:
            return False, None
        self._i += 1
        return True, None

    def release(self):
        pass


class TestDetMinScore:
    N = 12

    def _kosu(self, monkeypatch, frames_faces, face_cfg):
        import cv2

        from src import face as face_mod
        monkeypatch.setattr(face_mod, "_load_face",
                            lambda *a, **k: _SahteApp(frames_faces))
        monkeypatch.setattr(cv2, "VideoCapture", lambda src: _SahteCap(self.N))
        cfg = Config({"device": "cpu", "detect": {"vid_stride": 1}, "face": face_cfg})
        return face_mod.run_face("sahte.mp4", cfg)

    FACE_CFG = {"det_min_score": 0.60, "min_track_move": 0.05,
                "calm_step": 0.05, "min_calm_frac": 0.30}

    def test_skor_alti_tespit_tracke_girmez_raw_sayar(self, monkeypatch):
        """0.60 altı tespit (doku bandı) track'lere hiç girmemeli ama
        raw_detections teşhis için saymalı; sakin adımlarla gezinen gerçek
        yüz sayılmalı."""
        # yüz: kare başına 1 px kayma = 0.025 × boyut (sakin), toplam 11 px gezinti
        ff = [[_SahteYuz((100 + i, 100, 140 + i, 140), 0.9, [0.0, 1.0, 0.0]),
               _SahteYuz((300, 300, 340, 340), 0.55, [1.0, 0.0, 0.0])]
              for i in range(self.N)]
        res = self._kosu(monkeypatch, ff, dict(self.FACE_CFG))
        assert res.raw_detections == 2 * self.N   # düşük skorlular da raw'da
        assert res.detections == 1                # yalnız gerçek yüz sayıldı

    def test_skor_ustu_donmus_doku_finalize_elemesinde_gider(self, monkeypatch):
        """Skor tabanını geçen ama hiç kımıldamayan 'yüz' (yüksek skorlu duvar
        deseni) doku filtresiyle finalize'da elenmeli."""
        ff = [[_SahteYuz((300, 300, 340, 340), 0.85, [1.0, 0.0, 0.0])]
              for _ in range(self.N)]
        res = self._kosu(monkeypatch, ff, dict(self.FACE_CFG))
        assert res.raw_detections == self.N
        assert res.detections == 0


# ── Yüz: gallery bellek sınırı (kompaktla + emekliye ayır) ─────────
class TestGalleryKompakt:
    ESIK = 0.30   # config face.reid_threshold varsayılanı

    def test_sinir_altinda_dokunulmaz(self):
        g = [_sahte_track(1, [1.0, 0.0, 0.0]), _sahte_track(2, [0.0, 1.0, 0.0])]
        retired: list = []
        out = _compact_gallery(g, retired, 2, self.ESIK)
        assert out is g and retired == []

    def test_dedup_sinira_indirirse_emekli_yok(self):
        """Aynı kişinin iki girdisi birleşince sınır sağlanır → retired boş kalır."""
        g = [_sahte_track(1, [1.0, 0.0, 0.0], 50),
             _sahte_track(2, [0.95, 0.05, 0.0], 5),     # 1 ile aynı kişi
             _sahte_track(3, [0.0, 1.0, 0.0], 20)]
        retired: list = []
        out = _compact_gallery(g, retired, 2, self.ESIK)
        assert len(out) == 2 and retired == []
        assert sum(t.n_frames for t in out) == 75   # 50+5 birleşti, 20 ayrı

    def test_fazlalik_en_dusuk_n_frames_emekliye(self):
        """Dedup yetmezse en az görülen track retired'a gider — final sayımda kalır."""
        g = [_sahte_track(1, [1.0, 0.0, 0.0], 50),
             _sahte_track(2, [0.0, 1.0, 0.0], 20),
             _sahte_track(3, [0.0, 0.0, 1.0], 5)]        # üçü farklı kişi
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


class TestTekMakineKipi:
    """Redis yoksa worker olayları doğrudan DB'ye yazar (YerelBus).

    Docker'sız Windows kurulumunun temeli: Redis + ingestor olmadan da
    olaylar ve alarmlar aynı kurallarla üretilmeli.
    """

    def _bus(self, tmp_path, monkeypatch):
        # open_store önce DATABASE_URL'e bakar; test gerçek Postgres'e yazmasın
        monkeypatch.delenv("DATABASE_URL", raising=False)
        cfg = Config({"paths": {"db_path": str(tmp_path / "t.db")},
                      "plate": {"alert_min_reads": 2}})
        return YerelBus(cfg)

    def test_olaylar_dogrudan_dbye_yazilir(self, tmp_path, monkeypatch):
        bus = self._bus(tmp_path, monkeypatch)
        st = BusStore(bus)
        st.add_count_event("giris", 7, "in", "kapi", 12.5, 300)
        publish(bus, "health", "giris", {"status": "ok", "fps": 24.0})
        assert len(bus.store.recent_events(tur="count")) == 1
        assert bus.store.latest_health()[0]["status"] == "ok"
        bus.close()

    def test_alarm_esigi_tek_makinede_de_gecerli(self, tmp_path, monkeypatch):
        bus = self._bus(tmp_path, monkeypatch)
        bus.store.add_watch_plate("34ABC123", "test aracı", "watch")
        bus.store.commit()
        st = BusStore(bus)
        st.add_plate_event("otopark", "34ABC123", 0.9, 1, 20.0, 500)   # eşik altı
        assert bus.store.recent_alerts() == []
        st.add_plate_event("otopark", "34ABC123", 0.9, 3, 21.0, 520)   # eşik üstü
        assert len(bus.store.recent_alerts()) == 1
        bus.close()

    def test_bozuk_olay_akisi_durdurmaz(self, tmp_path, monkeypatch):
        bus = self._bus(tmp_path, monkeypatch)
        # 'plate' anahtarı olmayan yük -> isle() KeyError verir, yutulmalı
        publish(bus, "plate", "otopark", {"conf": 0.9})
        st = BusStore(bus)
        st.add_count_event("giris", 1, "in", "", 1.0, 1)   # sonrası çalışmaya devam
        assert len(bus.store.recent_events(tur="count")) == 1
        bus.close()
