#!/usr/bin/env python3
"""Niyet kapısı — bağımsız inceleme (incele.py) 8-11. tur regresyonları.

Her vaka bir P1 bulgusudur: önce kırmızı yazıldı, sonra düzeltildi.
tests/test_route_niyet.py dosya-boyutu eşiğine dayandığı için ayrıldı;
ölçülen ilk vakalar ve 5-7. tur oradadır.
"""
import importlib.util
import os
import sys
import tempfile
import unittest

# Keşif `tests/`i sys.path'e koyar, `python3 -m unittest tests.test_x` koymaz.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortam import pyyaml_gerekir  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "route", os.path.join(ROOT, "bin", "route.py"))
route = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(route)


@pyyaml_gerekir
class IncelemeTurlariTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = route.load_rules()

    def pick(self, prompt):
        task_class, primary, extras, _hits, explicit = route.route(
            prompt, self.cfg)
        return task_class, (primary or {}).get("skill"), extras, explicit

    # --- incele.py P1 bulguları, 12. tur (PR #49'da ertelendi) ---

    def test_unlu_dusmeli_anma_adi_da_isarettir(self):
        # P1: "metin" ünlü düşmesiyle çekilir ("metni", "metnini") ve anma
        # işareti listesi kökü olduğu gibi arıyordu — salt-okunur alıntı
        # isteği kullanıcının emri sanılıp code-change'e gidiyordu.
        for prompt in ('şu metni "kodu düzelt ve uygula" incele',
                       '"kodu düzelt ve uygula" metnini incele'):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "research")

    def test_birlesik_fiil_cumle_sinirini_asmaz(self):
        # P1: yardımcı fiil araması noktalamayı aşıyordu; ÖNCEKİ cümlenin
        # okuma adı sonraki cümlenin "yap"ına bağlanıp gerçek iş emrini
        # okuma sanıyordu. Alıntı bağlamasındaki _SINIR ölçüsü burada da
        # geçerlidir — birleşik fiilin adı ile yardımcısı aynı cümlededir.
        for prompt in ("araştırma tamam; migration yap",
                       "tarama tamam. testleri yap"):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "code-change")

    def test_kelime_icindeki_nokta_cumle_sonu_degildir(self):
        # P1 (12. turun kendi düzeltmesinden çıktı): cümle sınırı ham
        # metinde arandığı için dosya adındaki nokta ("foo.py") cümleyi
        # bölüyor, birleşik fiil kurulamıyor ve salt-okunur istek yazmaya
        # dönüyordu. Nokta ancak kelimenin İÇİNDE değilse sınırdır.
        for prompt in ("güvenlik analizini foo.py üzerinde yap",
                       "kod incelemesini route.py için yap"):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "research")

    def test_komut_uyarisi_turun_siniriyla_ayni_olcuyu_kullanir(self):
        # P1: _sinirli zorunlu skill'i TURUN sınıfına göre düşürürken
        # render'ın /komut dalı "herhangi bir profilde var mı" diye
        # soruyordu. Bu turda izinsiz olan skill için "onu yükle" denmesi,
        # aynı kararı iki farklı ölçüye bağlamaktır.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".agents", "skills", "yerel-skill"))
            pd = os.path.join(tmp, ".agents", "capability-profiles")
            os.makedirs(pd)
            with open(os.path.join(pd, "research.yml"), "w",
                      encoding="utf-8") as fh:
                fh.write("task_class: research\nskills:\n  - yerel-skill\n")
            cfg = {"rules": [{"skill": "yerel-skill",
                              "task_class": "code-change",
                              "risk": "approval",
                              "triggers": ["deneme"]}],
                   "fallback": {"task_class": "research"}}
            context, _s = route.render("/yerel-skill deneme", cfg, pdir=tmp)
            self.assertIn("izin sınırı dışında", context)
            self.assertNotIn("onu yükle", context)

    # --- incele.py P1 bulguları, 11. tur (PR #49) ---

    def test_anma_sonrasi_pencere_de_kelimeyle_sinirli(self):
        # P1: 10. turda ÖNCESİ kelimeyle sınırlandı ama SONRASI cümle
        # sınırına kadar serbest kaldı — uzaktaki "mesaj" alıntıya bağlanıp
        # kullanıcının emrini siliyordu.
        tc, _s, _e, _x = self.pick(
            '"auth açığını düzelt" ve yaptıklarını mesaj olarak raporla')
        self.assertEqual(tc, "code-change")

    def test_hal_eki_okuma_adini_nesne_yapmaz(self):
        # P1: "analizden sonra düzeltmeyi yap" — ayrılma hâlindeki ad
        # yardımcı fiilin NESNESİ değildir; birleşik fiil kurulmaz.
        for prompt in ("analizden sonra düzeltmeyi yap",
                       "incelemeden sonra düzeltmeyi yap"):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "code-change")

    def test_zorunlu_skill_de_izin_sinirina_tabidir(self):
        # P1: süzme yalnız extras'a uygulanıyordu; profilinden çıkarılmış
        # skill ZORUNLU kılınabiliyordu — sınır önerinin değil, dayatmanın
        # da üstünde olmalı.
        with tempfile.TemporaryDirectory() as tmp:
            pd = os.path.join(tmp, ".agents", "capability-profiles")
            os.makedirs(pd)
            with open(os.path.join(pd, "research.yml"), "w",
                      encoding="utf-8") as fh:
                fh.write("task_class: research\nskills:\n"
                         "  - research-with-evidence\n")
            tc, primary, _e, _h, _x = route.route(
                "login akışını güvenlik açısından incele", self.cfg, pdir=tmp)
            self.assertEqual(tc, "research")
            self.assertIsNone(primary,
                              "profil dışı skill zorunlu kılındı")

    # --- incele.py P1 bulguları, 10. tur (PR #49) ---

    def test_anma_baglama_kelimeyle_olculur_karakterle_degil(self):
        # P1: 9. turun komşuluk penceresi KARAKTER sayıyordu; bağlaç
        # kısalınca ("ardından" → "sonra") aynı işaret ikinci alıntıya da
        # ulaşıyordu. Bağlama artık kelimeyle ölçülür ve noktalama
        # sınırında kesilir.
        for prompt in ('"router çıktısı" ifadesini incele; sonra '
                       '"auth açığını düzelt"',
                       '"router çıktısı" ifadesini incele ve sonra '
                       '"auth açığını düzelt"'):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "code-change")

    def test_unlu_biten_adda_ikinci_cogul_iyelik(self):
        # P1: "incelemenizi" (inceleme+niz+i) ad çekimi sayılmıyordu.
        for prompt in ("bu PR için güvenlik incelemenizi yapın",
                       "kapsamlı araştırmanızı yapın"):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "research")

    def test_hafif_fiil_araya_giren_kelimeye_ragmen_taninir(self):
        # P1: yardımcı fiil yalnız adın HEMEN ardındaysa tanınıyordu;
        # "analizini detaylı yap" arada sıfat olduğu için yazma sayılıyordu.
        for prompt in ("login akışının güvenlik analizini detaylı yap",
                       "kod tabanının incelemesini çok kapsamlı yap"):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "research")

    def test_hafif_fiil_penceresi_uzak_fiili_yutmaz(self):
        # Negatif kontrol: ad ile fiil arasındaki mesafe büyükse birleşik
        # fiil değildir — "testleri yap" gerçek iş emridir.
        tc, _s, _e, _x = self.pick("analiz raporunu oku ve testleri yap")
        self.assertEqual(tc, "code-change")

    # --- incele.py P1 bulguları, 9. tur (PR #49) ---

    def test_egri_tek_tirnak_da_alintidir(self):
        # P1: ‘…’ (U+2018/2019) tanınmıyordu — düz tırnak tanınırken eğri
        # tırnak tanınmaması, aynı cümleyi klavyeye göre farklı sınıflara
        # yolluyordu.
        tc, _s, _e, _x = self.pick(
            "router çıktısındaki ‘kodu düzelt ve uygula’ ifadesini incele")
        self.assertEqual(tc, "research")

    def test_anma_isareti_alinti_basina_baglanir(self):
        # P1: tek bir anma işareti metindeki TÜM alıntıları siliyordu;
        # ikinci alıntı kullanıcının gerçek emriyken yok oluyordu.
        tc, _s, _e, _x = self.pick(
            '"router çıktısı" ifadesini incele; ardından '
            '"auth açığını düzelt"')
        self.assertEqual(tc, "code-change")

    def test_ikinci_cogul_iyelik_ad_ceki(self):
        # P1: -inizi biçimi ad çekimi sayılmıyordu.
        tc, _s, _e, _x = self.pick("bu PR için güvenlik analizinizi yapın")
        self.assertEqual(tc, "research")

    # --- incele.py P1 bulguları, 8. tur (PR #49) ---

    def test_anma_isareti_alinti_disinda_ve_kelime_siniriyla_aranir(self):
        # P1: işaret TÜM metinde ve kelime sınırı olmadan aranıyordu —
        # "login" içindeki "log" anma sanılıp kullanıcının kendi emrini
        # yok ediyordu. İşaret alıntının DIŞINDA ve tam kelime olmalı.
        tc, _s, _e, _x = self.pick(
            '"login açığını düzelt" ve yaptıklarını raporla')
        self.assertEqual(tc, "code-change")

    def test_unlu_biten_okuma_adi_kaynastirma_ekini_alir(self):
        # P1: _AD_EK ünlüyle biten adın -yı/-yi çekimini tanımıyordu;
        # "araştırmayı yap" salt-okunur istekken yazma sayılıyordu.
        for prompt in ("gerekli araştırmayı yap",
                       "bu değerlendirmeyi yap",
                       "kapsamlı taramayı yapalım"):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "research")


if __name__ == "__main__":
    unittest.main()
