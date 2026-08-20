#!/usr/bin/env python3
"""Olay (incident) sınıfı eskalasyon testleri — bin/route.py.

tests/test_route.py dosya-boyutu eşiğine dayandığı için ayrıldı (2026-08-12,
test_route_komut.py ve test_route_niyet.py ile aynı gerekçe). Burada yalnız
incident sınıfına eskalasyon vakaları yaşar; genel tablo eşleşmeleri
test_route.py'de kalır.
"""
import importlib.util
import os
import sys
import unittest

# Keşif `tests/`i sys.path'e koyar, `python3 -m unittest tests.test_x` koymaz.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortam import pyyaml_gerekir  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "route", os.path.join(ROOT, "bin", "route.py"))
route = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(route)


# Sınıfın TAMAMI yönlendirme tablosunu okur; tablo yaml'dır. PyYAML yoksa
# setUpClass çökerdi ve sınıfın tüm testleri süitten YOK OLURDU. Atlama
# sayıyı korur, gerekçeyi gösterir.
@pyyaml_gerekir
class OlayEskalasyonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = route.load_rules()

    def pick(self, prompt):
        task_class, primary, extras, _hits, explicit = route.route(
            prompt, self.cfg)
        return task_class, (primary or {}).get("skill"), extras, explicit

    def test_olay_istegi_incident_sinifi_uretir(self):
        """incident profili tanımlı ama hiçbir kural onu üretmiyordu.

        Ulaşılamayan profil, olmayan korumadır: acil üretim işi normal
        code-change gibi sınıflanırsa olay disiplini hiç devreye girmez.
        """
        for istem in ("prod çöktü, acil müdahale lazım",
                      "serviste kesinti var, üretim hatası"):
            tc, _s, _e, _x = self.pick(istem)
            self.assertEqual(tc, "incident", istem)

    def test_ayni_skill_iki_kuralda_ise_baglam_secer(self):
        """Aynı skill birden çok kuralda olabilir; /komut ilkine takılmamalı.

        implement-change hem code-change hem incident kuralında geçiyor.
        Açık komut ilk eşleşende dururken olay kuralı ERİŞİLEMEZ kalıyordu:
        acil üretim işi normal kod işi gibi sınıflanırdı.
        """
        tc, skill, _e, _x = self.pick("/implement-change prod çöktü acil müdahale")
        self.assertEqual((tc, skill), ("incident", "implement-change"))

        tc, skill, _e, _x = self.pick("/implement-change kullanıcı endpointi ekle")
        self.assertEqual((tc, skill), ("code-change", "implement-change"))

    def test_acik_komut_kural_seciminde_ozgulluk_de_sayilir(self):
        """Komut kuralı seçimi tetik SAYISI + ÖZGÜLLÜK ister, yalnız sayı değil.

        İnceleme bulgusu (PR #40): '/implement-change prod çöktü' isteminde
        komut adındaki 'implement' kelimesi GENEL kurala tetik sayılıyor;
        tek olay tetiği ile berabere kalınca tablo sırası kazanıyor ve
        specificity-3 olay kuralı yeniliyordu. Acil iş normal kod işi gibi
        sınıflanıyordu — puanlamayla aynı kural: eşitlikte özgül kazanır.
        """
        tc, skill, _e, _x = self.pick("/implement-change prod çöktü")
        self.assertEqual((tc, skill), ("incident", "implement-change"))

    def test_olay_sinifi_eskalasyonu_sayiya_bakmaz(self):
        """Olay tetiği görüldüyse sınıf incident'a ESKALE olur — sayı yarışı yok.

        İnceleme bulguları (PR #40, ardışık 3 tur): sayı-tabanlı her formül
        yenildi — önce 2 genel fiil tek olay tetiğini ezdi, çarpım eşiği
        kaydırınca 4 fiil ezdi. Yarış kazanılamaz (grilling dersi, PR #39).
        Eskalasyon varlığa bakar, sayıya değil: AGENTS.md 'eskalasyon yalnız
        yukarı' ilkesinin routing karşılığı.
        """
        for istem in ("prod çöktü, düzelt ve uygula",
                      "prod çöktü; düzelt, uygula, kodla ve test yaz",
                      "canlıda hata var hemen düzelt"):
            tc, _s, _e, _x = self.pick(istem)
            self.assertEqual(tc, "incident", istem)

    def test_soru_bicimi_olay_sinifini_dusurmez(self):
        # Soru zorunlu skill dayatmayı engeller, SINIFI düşürmez: çökmüş
        # prod hakkında soru da olay bağlamında ele alınır.
        tc, skill, _e, _x = self.pick("prod çöktü, bakabilir misin?")
        self.assertEqual(tc, "incident")
        self.assertIsNone(skill)

    def test_olay_tetikleri_gundelik_isle_karismaz(self):
        # 'kesinti' öneki 'kesintisiz'i, 'servis durdu' alt-dizesi 'servis
        # durdurma'yı yakalıyordu — tetikler somut olay ifadeleri olmalı.
        for istem in ("kesintisiz dağıtım pipeline'ı ekle",
                      "servis durdurma butonu ekle"):
            tc, _s, _e, _x = self.pick(istem)
            self.assertNotEqual(tc, "incident", istem)

    def test_acik_komutta_da_olay_eskalasyonu_calisir(self):
        """Komut SKILL seçimidir, SINIF seçimi değil — eskalasyon çalışır.

        İnceleme bulgusu: '/implement-change prod çöktü; düzelt, uygula,
        kodla ve test yaz' komut yolunda eskalasyon atlanıp code-change
        kalıyordu. Kullanıcının seçtiği şey skill; sınıf bağlamdan gelir.
        Sınır: seçilen skill incident profilinde İZİNLİ değilse (grilling
        gibi) kullanıcı sınıfı korunur — read-only skill'e yazma profili
        giydirilmez.
        """
        tc, skill, _e, _x = self.pick(
            "/implement-change prod çöktü; düzelt, uygula, kodla ve test yaz")
        self.assertEqual((tc, skill), ("incident", "implement-change"))
        # incident profilinde olmayan skill'de sınıf korunur
        tc, _s, _e, _x = self.pick("/grilling prod çöktü planı netleştir")
        self.assertEqual(tc, "research")

    def test_primarysiz_olayin_riski_auto_gorunmez(self):
        # 'prod çöktü, bakabilir misin?' → sınıf incident, zorunlu skill yok;
        # başlıktaki risk sınıftan türemeli, 'auto' yanlış güven verir.
        cfg = route.load_rules()
        context, _s = route.render("prod çöktü, bakabilir misin?", cfg,
                                   pdir=ROOT)
        self.assertIn("Sınıf: incident", context)
        self.assertIn("Risk: approval", context)


if __name__ == "__main__":
    unittest.main()
