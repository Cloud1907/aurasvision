#!/usr/bin/env python3
"""İnceleme döngüsünün ÇIKIŞLARI — P1, tur tavanı, yeniden deneme, artımlı diff.

Ayrı dosya çünkü ayrı soru: `test_incele.py` "kapı doğru karar veriyor mu"
diye sorar, bu dosya "kapı KAPANIYOR mu" diye. İkisi aynı dosyadayken 516
satıra çıktı ve kalite ratchet'inin 400 satır sınırına dayandı — sınır,
ayrılması gereken iki sorumluluğu gösteriyordu (aynı gerekçe: bin/surec.py).

Codex ve gh burada da KOŞMAZ; dış dünya `SahteKos` ile taklit edilir.
"""
import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "incele", os.path.join(ROOT, "bin", "incele.py"))
incele = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(incele)

TEMIZ = {"P0": [], "P1": [], "P2": []}


# --- Döngü maliyeti ölçümü (2026-08-12) -----------------------------------
# 9 PR'da 62 inceleme turu, tur arası medyan 16 dk, toplam ~17 saat. 62
# hükmün YALNIZ 2'si temizdi. Dağılım: 41 P1, 2 P0, 9 "ayrıştırılamadı",
# 7 "tutarsız". Kapı doğru çalışıyordu ama ÇIKIŞI yoktu: her düzeltme yeni
# inceleme yüzeyi üretiyor, Codex orada yeni bir P1 buluyordu. Aşağıdaki
# dört sınıf o döngünün dört çıkışını kilitler.

class P1BloklamazTest(unittest.TestCase):
    """P1 merge blokeri OLMAKTAN ÇIKTI (62 ENGEL'in 41'i buydu).

    "Bloklamamak" ile "görmezden gelmek" aynı şey değildir: bulgu PR
    yorumunda kalır ve karar İNSAN'a gider — yalnız otomatik düzelt-ve-yeniden-
    incele döngüsünü tetiklemez.
    """

    def test_p1_engel_uretmez(self):
        b = {"P0": [], "P1": ["api.py:9 kaynak sızıntısı"], "P2": []}
        k, g = incele.karar("auto", b, True, True)
        self.assertEqual(k, "insan")
        self.assertIn("P1", g)

    def test_p1_otomatik_merge_de_ettirmez(self):
        # Auto riskte bile: bulgu varken makine kendi başına birleştiremez.
        b = {"P0": [], "P1": ["x"], "P2": []}
        self.assertEqual(incele.karar("auto", b, True, True)[0], "insan")

    def test_p0_hala_engel(self):
        b = {"P0": ["yetki yok"], "P1": ["x"], "P2": []}
        self.assertEqual(incele.karar("auto", b, True, True)[0], "engel")

    def test_p1_bulgusu_govdede_gorunur_kalir(self):
        b = {"P0": [], "P1": ["route.py:196 açık komut reddedilmiyor"], "P2": []}
        g = incele.ozet_govde("auto", b, "1 bulgu", "insan", "P1 var", "1/1 pass")
        self.assertIn("route.py:196", g)


class TurTavaniTest(unittest.TestCase):
    """Döngünün üst sınırı: N turdan sonra karar makinenin değil insanın.

    PR #39, 16 turun sonunda insan override'ıyla kapandı — yani tavan zaten
    vardı, sadece SİSTEMDE değil insanın sabrındaydı. Tavan asla `merge`
    üretmez: yalnız ENGEL'i İNSAN'a çevirir.
    """

    def test_tavan_altinda_p0_engel_kalir(self):
        b = {"P0": ["yetki yok"], "P1": [], "P2": []}
        for tur in (1, 2, 3):
            with self.subTest(tur=tur):
                self.assertEqual(
                    incele.karar("auto", b, True, True, tur=tur)[0], "engel")

    def test_tavan_asilinca_p0_insana_gider(self):
        b = {"P0": ["yetki yok"], "P1": [], "P2": []}
        k, g = incele.karar("auto", b, True, True, tur=4)
        self.assertEqual(k, "insan")
        self.assertIn("tavan", g.lower())

    def test_tavan_asilinca_okunamadi_insana_gider(self):
        k, _g = incele.karar("auto", TEMIZ, True, okunabildi=False, tur=4)
        self.assertEqual(k, "insan")

    def test_tavan_asilinca_tutarsizlik_insana_gider(self):
        k, _g = incele.karar("auto", TEMIZ, True, True, tutarli=False, tur=4)
        self.assertEqual(k, "insan")

    def test_tavan_deny_sinifini_gevsetmez(self):
        # Tavan inceleyicinin FİKRİNİ eskale eder; politikayı değil.
        b = {"P0": ["x"], "P1": [], "P2": []}
        self.assertEqual(incele.karar("deny", b, True, True, tur=9)[0], "engel")

    def test_tavan_kirmizi_ciyi_gevsetmez(self):
        # CI ölçümdür, hüküm değil: tavan onu aşamaz.
        self.assertEqual(
            incele.karar("auto", TEMIZ, False, True, tur=9)[0], "engel")

    def test_tavan_asla_merge_uretmez(self):
        b = {"P0": ["x"], "P1": ["y"], "P2": []}
        for tur in (4, 10, 99):
            with self.subTest(tur=tur):
                self.assertNotEqual(
                    incele.karar("auto", b, True, True, tur=tur)[0], "merge")


class MarkerTest(unittest.TestCase):
    """Tur sayacı ve incelenen SHA, PR yorumunun kendisinde taşınır.

    Neden yerel dosya değil: kapı farklı makinelerden koşuluyor ve yerel
    durum dosyası agent'ın silebildiği bir şeydir. PR yorumu hem kalıcı hem
    görünür — kaydın kaybolması turu SIFIRLAR, yani fail-closed.
    """

    def test_marker_govdeye_yazilir(self):
        g = incele.ozet_govde("auto", TEMIZ, "TEMIZ", "merge", "ok", "1/1",
                              tur=2, head_sha="abc1234", p0gecmis=True)
        self.assertIn("tur=2", g)
        self.assertIn("abc1234", g)

    def test_marker_okunur(self):
        g = incele.ozet_govde("auto", TEMIZ, "TEMIZ", "engel", "x", "1/1",
                              tur=3, head_sha="deadbee", p0gecmis=True)
        d = incele.marker_oku(["alakasız yorum", g])
        self.assertEqual(d["tur"], 3)
        self.assertEqual(d["sha"], "deadbee")
        self.assertTrue(d["p0gecmis"])

    def test_marker_yoksa_sifirdan(self):
        d = incele.marker_oku(["hiç inceleme yorumu yok"])
        self.assertEqual(d["tur"], 0)
        self.assertEqual(d["sha"], "")
        self.assertFalse(d["p0gecmis"])

    def test_son_marker_gecerli(self):
        g1 = incele.ozet_govde("auto", TEMIZ, "TEMIZ", "engel", "x", "1/1",
                               tur=1, head_sha="aaa", p0gecmis=True)
        g2 = incele.ozet_govde("auto", TEMIZ, "TEMIZ", "engel", "x", "1/1",
                               tur=2, head_sha="bbb", p0gecmis=False)
        d = incele.marker_oku([g1, g2])
        self.assertEqual(d["tur"], 2)
        self.assertEqual(d["sha"], "bbb")
        # p0 geçmişi SÖNMEZ: bir kez P0 görülen PR'da artımlı mod kapalı kalır.
        self.assertFalse(d["p0gecmis"])  # gövdeyi üreten çağrı öyle dedi


class SahteKos:
    """`incele._kos` yerine geçer: komuta göre sabit cevap, çağrı kaydı.

    Codex ve gh testte KOŞMAZ — kapı kararı dış dünyaya bağlı olmadan
    doğrulanır (dosyanın en baştaki sözleşmesi).
    """

    def __init__(self, checks="kernel\tpass\t1s\tu", head="head1",
                 yorumlar=None, incelemeler=None, dosyalar="docs/a.md",
                 inceleme_kodu=0):
        self.checks, self.head = checks, head
        self.yorumlar = yorumlar or []
        self.incelemeler = list(incelemeler or [])
        self.dosyalar = dosyalar
        self.inceleme_kodu = inceleme_kodu   # ≠0 → codex-review.sh çöktü
        self.cagrilar = []

    @property
    def inceleme_sayisi(self):
        return sum(1 for c in self.cagrilar if c[0] == "bash")

    @property
    def son_base(self):
        """Son inceleme çağrısına geçen --base değeri (yoksa '')."""
        for c in reversed(self.cagrilar):
            if c[0] == "bash":
                for a in c:
                    if a.startswith("--base="):
                        return a.split("=", 1)[1]
                return ""
        return ""

    def __call__(self, *arg, girdi=None, timeout=None):
        self.cagrilar.append(arg)
        if arg[0] == "bash":
            return (self.inceleme_kodu,
                    (self.incelemeler.pop(0) if self.incelemeler else ""),
                    "timed out" if self.inceleme_kodu else "")
        if "checks" in arg:
            return 0, self.checks, ""
        if "diff" in arg:
            return 0, "+kod", ""
        if "--json" in arg:
            alan = arg[arg.index("--json") + 1]
            if alan == "comments":
                return 0, json.dumps(
                    {"comments": [{"body": b} for b in self.yorumlar]}), ""
            if alan == "headRefOid":
                return 0, self.head, ""
            if alan == "files":
                return 0, self.dosyalar, ""
        return 0, "", ""


class _KosYamasi(unittest.TestCase):
    """`incele._kos`'u sahteyle değiştirip test sonunda geri koyar."""

    def kur(self, **kw):
        sahte = SahteKos(**kw)
        gercek = incele._kos
        incele._kos = sahte
        self.addCleanup(lambda: setattr(incele, "_kos", gercek))
        return sahte


TEMIZ_CIKTI = "İnceleme yapıldı.\nSONUC: TEMIZ\n"
BOZUK_CIKTI = "codex: connection reset by peer\n"
P1_CIKTI = "[P1] a.py:1 — sorun — senaryo\nSONUC: 1 bulgu (en yuksek: P1)\n"


class YenidenDenemeTest(_KosYamasi):
    """Ayrıştırma hatası KOD sorunu değil BİÇİM sorunudur — 62 ENGEL'in 16'sı.

    Bir kez daha sormak, tam bir insan turundan (medyan 16 dk) ucuzdur.
    İkinci deneme de okunamazsa fail-closed korunur: 'okunamadı' hâlâ
    'temiz' değildir.
    """

    def test_okunamayan_cikti_bir_kez_yeniden_denenir(self):
        s = self.kur(incelemeler=[BOZUK_CIKTI, TEMIZ_CIKTI])
        d = incele.topla("7")
        self.assertEqual(s.inceleme_sayisi, 2)
        self.assertTrue(d["okunabildi"])

    def test_tutarsiz_hukum_de_yeniden_denenir(self):
        # Bulgu var ama hüküm TEMIZ diyor → tutarsız → yeniden sor.
        tutarsiz = "[P1] a.py:1 — sorun — senaryo\nSONUC: TEMIZ\n"
        s = self.kur(incelemeler=[tutarsiz, P1_CIKTI])
        d = incele.topla("7")
        self.assertEqual(s.inceleme_sayisi, 2)
        self.assertTrue(d["tutarli"])

    def test_ikinci_deneme_de_okunamazsa_fail_closed(self):
        s = self.kur(incelemeler=[BOZUK_CIKTI, BOZUK_CIKTI])
        d = incele.topla("7")
        self.assertEqual(s.inceleme_sayisi, 2)
        self.assertFalse(d["okunabildi"])
        self.assertEqual(
            incele.karar(d["risk"], d["bulgular"], d["ci_yesil"],
                         d["okunabildi"], tur=1)[0], "engel")

    def test_temiz_ciktida_ikinci_cagri_yapilmaz(self):
        # Yeniden deneme bir ~150s'lik Codex çağrısıdır; bedava değildir.
        s = self.kur(incelemeler=[TEMIZ_CIKTI, TEMIZ_CIKTI])
        incele.topla("7")
        self.assertEqual(s.inceleme_sayisi, 1)

    def test_zaman_asiminda_yeniden_denenmez(self):
        """Zaman aşımı BİÇİM sorunu değildir — tekrarlamak bütçeyi ikiye
        katlar (900s → 1800s) ve asılı sürecin üstüne ikincisini yığar.

        Bu bekçi ölçümle geldi: kapı kendi PR'ında (#48) 15 dk bütçeye
        dayandı; yeniden deneme onu 30 dk yapacaktı. Zaman aşımının çaresi
        tekrar değil, `zaman_asimi_notu`nun yazdığı sıradır.
        """
        s = self.kur(inceleme_kodu=1, incelemeler=["", ""])
        d = incele.topla("7")
        self.assertEqual(s.inceleme_sayisi, 1, "zaman aşımı tekrarlandı")
        self.assertFalse(d["okunabildi"])
        self.assertFalse(d["yeniden"])

    def test_zaman_asimi_yine_de_engel(self):
        # Tekrar etmemek, gevşemek değildir: karar hâlâ fail-closed.
        s = self.kur(inceleme_kodu=1, incelemeler=[""])
        d = incele.topla("7")
        self.assertEqual(
            incele.karar(d["risk"], d["bulgular"], d["ci_yesil"],
                         d["okunabildi"], tutarli=d["tutarli"], tur=1)[0],
            "engel")
        self.assertIn("zaman aşımı", d["hata"].lower())
        self.assertEqual(s.inceleme_sayisi, 1)


class ArtimliIncelemeTest(_KosYamasi):
    """İnceleme her tur TÜM birikmiş diff'e bakıyordu: düzeltme kodu bir
    sonraki turun inceleme yüzeyi oluyordu. Artımlı mod o üretimi keser.

    P0 görülmüş PR'da KAPALI — P0'ın gerçekten gittiğini görmek tam diff
    ister; hız için doğruluktan vazgeçilmez.
    """

    def _yorum(self, tur, sha, p0gecmis=False):
        return incele.ozet_govde("auto", TEMIZ, "TEMIZ", "engel", "x", "1/1",
                                 tur=tur, head_sha=sha, p0gecmis=p0gecmis)

    def test_ilk_turda_base_yok(self):
        s = self.kur(incelemeler=[TEMIZ_CIKTI])
        incele.topla("7")
        self.assertEqual(s.son_base, "")

    def test_onceki_sha_artimli_base_olur(self):
        s = self.kur(head="yeni2", incelemeler=[TEMIZ_CIKTI],
                     yorumlar=[self._yorum(1, "eski1")])
        incele.topla("7")
        self.assertEqual(s.son_base, "eski1")

    def test_p0_gecmisi_varsa_tam_diff(self):
        s = self.kur(head="yeni2", incelemeler=[TEMIZ_CIKTI],
                     yorumlar=[self._yorum(1, "eski1", p0gecmis=True)])
        incele.topla("7")
        self.assertEqual(s.son_base, "")

    def test_p0_gecmisi_sonraki_turlarda_da_hatirlanir(self):
        s = self.kur(incelemeler=[P1_CIKTI])
        d = incele.topla("7")
        self.assertFalse(d["p0gecmis"])
        s2 = self.kur(head="h2", incelemeler=[TEMIZ_CIKTI],
                      yorumlar=[self._yorum(1, "h1", p0gecmis=True)])
        d2 = incele.topla("7")
        self.assertTrue(d2["p0gecmis"], "P0 geçmişi sönmemeli")
        self.assertEqual(s2.son_base, "")

    def test_incelenmemis_sha_kaydedilmez(self):
        """Marker'daki `sha` = GERÇEKTEN incelenen commit.

        Zaman aşımına uğrayan tur hiçbir şey incelemez. SHA'yı yine de
        kaydetmek, bir sonraki turu "dalda yeni commit yok — önceki inceleme
        geçerli" hükmüne düşürüyordu: OLMAYAN bir incelemeye atıf. O hâlde
        zaman aşımından sonra aynı commit bir daha asla incelenemezdi
        (çıkış yalnız boş commit atmak). Canlı ölçüm, PR #48 tur 1→2.
        """
        g = incele.ozet_govde("auto", TEMIZ, "", "engel", "zaman aşımı", "1/1",
                              tur=1, head_sha="abc123", p0gecmis=False,
                              incelendi=False)
        self.assertEqual(incele.marker_oku([g])["sha"], "")

    def test_incelenen_sha_kaydedilir(self):
        g = incele.ozet_govde("auto", TEMIZ, "TEMIZ", "merge", "ok", "1/1",
                              tur=1, head_sha="abc123", p0gecmis=False,
                              incelendi=True)
        self.assertEqual(incele.marker_oku([g])["sha"], "abc123")

    def test_zaman_asimi_sonrasi_ayni_commit_yeniden_incelenir(self):
        # Uçtan uca: zaman aşımı turundan sonra dal kıpırdamasa BİLE Codex
        # yeniden çağrılmalı — yoksa kapı kalıcı ENGEL'e kilitlenir.
        bos = incele.ozet_govde("auto", TEMIZ, "", "engel", "zaman aşımı",
                                "1/1", tur=1, head_sha="ayni1",
                                p0gecmis=False, incelendi=False)
        s = self.kur(head="ayni1", incelemeler=[TEMIZ_CIKTI], yorumlar=[bos])
        d = incele.topla("7")
        self.assertEqual(s.inceleme_sayisi, 1, "zaman aşımı turu kapıyı kilitledi")
        self.assertFalse(d["degismedi"])
        self.assertEqual(d["tur"], 2)

    def test_head_degismediyse_yeniden_incelenmez(self):
        # Boş artımlı diff "TEMİZ" görünür ve önceki turun bulgusunu silerdi.
        s = self.kur(head="ayni1", incelemeler=[TEMIZ_CIKTI],
                     yorumlar=[self._yorum(1, "ayni1")])
        d = incele.topla("7")
        self.assertEqual(s.inceleme_sayisi, 0, "yeni commit yokken Codex çağrıldı")
        self.assertTrue(d["degismedi"])

    def test_degismemis_dal_merge_uretmez(self):
        k, g = incele.karar("auto", TEMIZ, True, True, degismedi=True)
        self.assertEqual(k, "insan")
        self.assertIn("yeni commit", g)

    def test_tur_sayaci_yorumdan_ilerler(self):
        self.kur(head="h9", incelemeler=[TEMIZ_CIKTI],
                 yorumlar=[self._yorum(1, "h1"), self._yorum(2, "h2")])
        self.assertEqual(incele.topla("7")["tur"], 3)


if __name__ == "__main__":
    unittest.main()
