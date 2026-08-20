#!/usr/bin/env python3
"""bin/niyet.py niyet kapısı regresyonları — okuma/mutasyon ayrımı.

Ölçülen yanlış yönlendirmeler (bağımsız inceleme 2026-08-12) ve incele.py
P1 turlarının (PR #43) kalıcı vakaları. tests/test_route.py dosya-boyutu
eşiğine dayandığı için ayrıldı; tablo/komut testleri orada yaşar.
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

_nspec = importlib.util.spec_from_file_location(
    "niyet", os.path.join(ROOT, "bin", "niyet.py"))
niyet = importlib.util.module_from_spec(_nspec)
_nspec.loader.exec_module(niyet)


@pyyaml_gerekir
class NiyetKapisiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = route.load_rules()

    def pick(self, prompt):
        task_class, primary, extras, _hits, explicit = route.route(
            prompt, self.cfg)
        return task_class, (primary or {}).get("skill"), extras, explicit

    # --- incele.py P1 bulguları, 7. tur (PR #49) ---

    def test_yerel_profilin_bilincli_dislamasi_onerilmez(self):
        # P1: süzme "skill_izinli=False → kapsam dışı" varsayıyordu; oysa
        # projenin YÖNETTİĞİ ama profilinden bilinçli ÇIKARDIĞI skill de
        # False döner. İkisini ayırmayan süzme, dışlamayı tavsiyeye çevirir.
        with tempfile.TemporaryDirectory() as tmp:
            pd = os.path.join(tmp, ".agents", "capability-profiles")
            os.makedirs(pd)
            with open(os.path.join(pd, "research.yml"), "w",
                      encoding="utf-8") as fh:
                fh.write("task_class: research\nskills:\n"
                         "  - research-with-evidence\n")
            sonuc = ("research", None, ["security-review", "dataviz"], [], None)
            _tc, _p, extras, _h, _x = route._sinirli(
                sonuc, lambda sk, tc: route._profil_disi(sk, tc, tmp))
            # security-review kanonikte YÖNETİLEN bir skill ama bu projenin
            # profilinde yok → bilinçli dışlama, önerilmez.
            self.assertNotIn("security-review", extras)
            # dataviz sistemin yönetmediği eklenti → kapsam dışı, dokunulmaz.
            self.assertIn("dataviz", extras)

    def test_okuma_adi_turemis_kelimeyi_yutmaz(self):
        # P1: okuma adları önekle eşleşiyordu — "analizör" ("analiz"+"ör")
        # okuma adı sanılıp gerçek geliştirme emrini okumaya çeviriyordu.
        tc, _s, _e, _x = self.pick("statik analizör yap")
        self.assertEqual(tc, "code-change")

    def test_cok_kelimeli_okuma_adi_eslesir(self):
        # P1: "gözden geçirme" tek önceki token'la karşılaştırıldığı için
        # HİÇ eşleşemiyordu — kural yazılmıştı ama çalışmıyordu.
        tc, _s, _e, _x = self.pick("kod tabanının gözden geçirmesini yap")
        self.assertEqual(tc, "research")

    def test_tirnak_ancak_anma_isaretiyle_yok_sayilir(self):
        # P1: tırnak içi her emir koşulsuz "anılan metin" sayılıyordu;
        # kullanıcı KENDİ emrini tırnaklarsa istek yazmadır. Anma işareti
        # (ifade, çıktı, cümle…) POZİTİF kanıt olarak aranır.
        tc, _s, _e, _x = self.pick(
            '"auth açığını düzelt" ve yaptıklarını raporla')
        self.assertEqual(tc, "code-change")
        # 5. tur çiti korunur: anma işareti varsa alıntı yine yok sayılır.
        tc2, _s2, _e2, _x2 = self.pick(
            "router çıktısındaki 'kodu düzelt ve uygula' ifadesini incele")
        self.assertEqual(tc2, "research")

    # --- niyet ayrımı: salt-okunur inceleme vs mutasyon (2026-08-12) ---
    # Bağımsız inceleme (Codex) iki turda da doğruladı: tek aşamalı kelime
    # puanlaması salt-okunur inceleme isteğini ALAN ADLARI yüzünden yazma
    # yetkili işe çeviriyordu. İki ölçülen vaka kalıcı regresyon:

    def test_salt_okunur_inceleme_alan_adlariyla_yazma_isine_donmez(self):
        # Ölçülen vaka 1: kernel-work tetikleri (router, kanıt, hafıza)
        # 3 puanla "incele"yi (1 puan) ezip code-change/approval üretiyordu.
        tc, skill, extras, _x = self.pick(
            "AurasAgents router, AurasPrime, kanıt kapıları ve hafıza "
            "sistemini eleştirel incele")
        self.assertEqual(tc, "research")
        self.assertEqual(skill, "research-with-evidence")
        # İlk tasarım kernel-work'ü "Ek skill" olarak öneride bırakıyordu;
        # inceleme 5. turu bunu izin sınırı ihlali saydı ve haklıydı —
        # salt-okunur turda yazma skill'i önerilmez (bkz.
        # test_salt_okunur_turda_oneri_de_izin_sinirina_tabidir).
        self.assertNotIn("kernel-work", extras)

    def test_inceleme_istemi_duzelt_kelimesiyle_mutasyona_donmez(self):
        # Ölçülen vaka 2: Codex'in kendi inceleme istemi içindeki "düzelt"
        # implement-change'i zorunlu kılıyordu. Türkçe emir cümle SONUNDADIR:
        # son niyet işareti okuma ise istek okumadır; "kod yazma" olumsuz
        # emirdir, yazma işareti sayılmaz.
        tc, skill, _e, _x = self.pick(
            "route.py yönlendirmesini eleştirel incele; neyi düzeltmemiz "
            "gerektiğini bulgu olarak raporla, kod yazma")
        self.assertEqual(tc, "research")
        self.assertNotEqual(skill, "implement-change")

    def test_mutasyon_dogrulaninca_yazma_kurali_kalir(self):
        # Niyet çiti iş emrini yutmamalı: son işaret yazma ise mutasyondur.
        _tc, skill, _e, _x = self.pick(
            "raporda bulduğun bug'ı incele ve düzelt")
        self.assertEqual(skill, "implement-change")

    def test_okunur_niyette_okunur_kural_yoksa_zorunlu_skill_yok(self):
        # Düşük güven: niyet okuma ama hiçbir okuma kuralı eşleşmedi —
        # zorunlu skill üretilmez. Eşleşen yazma kuralları da ÖNERİLMEZ:
        # öneri de profilin izin sınırına tabidir (inceleme 5. tur).
        tc, skill, extras, _x = self.pick(
            "çekirdek profillerini gözden geçir")
        self.assertIsNone(skill)
        self.assertEqual(tc, "research")
        self.assertNotIn("kernel-work", extras)

    # --- incele.py P1 bulguları (PR #43, 2026-08-12) — kalıcı regresyon ---

    def test_yazma_emri_sonda_raporla_olsa_da_mutasyondur(self):
        # P1: "son işaret kazanır" çok-eylemli gerçek mutasyonu okumaya
        # çeviriyordu. Yalın yazma emri ("ekle") varsa tur mutasyondur.
        _tc, skill, _e, _x = self.pick(
            "kullanıcı endpoint'ini ekle ve yaptığını raporla")
        self.assertEqual(skill, "implement-change")

    def test_routing_yazma_fiili_niyet_sozlugunde(self):
        # P1: "güzelleştir" routing tetiğiydi ama niyet sözlüğünde yoktu —
        # açık değişiklik emri zorunlu skill'siz kalıyordu.
        _tc, skill, _e, _x = self.pick("dashboard ekranını güzelleştir")
        self.assertEqual(skill, "designing-interfaces")

    def test_cekimli_olumsuz_ve_edilgen_yazma_isareti_sayilmaz(self):
        # P1: yalnız tam -ma/-me eki olumsuz sayılıyordu; "düzeltmeden"
        # gibi çekimli olumsuz ve "düzeltilmesi" gibi edilgen biçimler
        # yazma işareti sayılıp turu mutasyona çeviriyordu.
        for prompt in ("önce bulgularını raporla, kodu kesinlikle "
                       "düzeltmeden bırak",
                       "düzeltilmesi gerekenleri listele"):
            with self.subTest(prompt=prompt):
                tc, skill, _e, _x = self.pick(prompt)
                self.assertNotEqual(skill, "implement-change")
                self.assertEqual(tc, "research")

    def test_okuma_niyetinde_denetim_salt_okunur_profil_alir(self):
        # P1: intent:read kuralı code-change sınıfını koruyunca salt-okunur
        # denetim yazma profili açıyordu. Skill zorunlu kalır (golden),
        # sınıf okuma profiline iner; risk etiketi kuraldan gelir.
        tc, skill, _e, _x = self.pick(
            "login akışını güvenlik açısından incele")
        self.assertEqual(skill, "security-review")
        self.assertEqual(tc, "research")

    # --- incele.py P1 bulguları, 2. tur (PR #43) — ek beyaz-listesi ---

    def test_isim_govdesi_yazma_emri_sanilmaz(self):
        # P1: startswith morfem sınırı aramıyordu — "yapısını" içindeki
        # "yap" kökü mutasyon sayılıp kernel-work'ü zorunlu kılıyordu.
        tc, skill, extras, _x = self.pick("router yapısını eleştirel incele")
        self.assertEqual(tc, "research")
        self.assertEqual(skill, "research-with-evidence")
        self.assertNotIn("kernel-work", extras)   # öneri de sınıra tabi

    def test_edilgen_n_biçimi_yazma_isareti_sayilmaz(self):
        # P1: edilgen listesi -ıl/-il ile sınırlıydı; ünlüyle biten kökün
        # -n edilgeni ("eklenmesi") mutasyon sayılıyordu.
        tc, skill, _e, _x = self.pick(
            "eklenmesi gereken kontrolleri raporla")
        self.assertNotEqual(skill, "implement-change")
        self.assertEqual(tc, "research")

    def test_yukumluluk_fiil_ismi_mutasyondur(self):
        # P1: her -ma/-me devamı olumsuz sayılıyordu — "düzeltmemiz
        # gerekiyor" açık iş talebi salt-okunur profile düşüyordu.
        #
        # 2026-08-15 DÜZELTMESİ: eskiden bu vakada `security-review`
        # BİRİNCİL oluyordu (specificity 2 ile kazanıyordu) ve uygulama
        # işi denetim skill'ine gidiyordu. Mutasyon DOĞRULANMIŞKEN
        # okuma-niyetli kural birincil olamaz: iş uygulamadır, denetim ona
        # EŞLİK eder. Eval corpus'u bu simetriyi kalıcı vaka olarak tutar.
        tc, skill, extras, _x = self.pick(
            "auth kontrolünü düzeltmemiz gerekiyor")
        self.assertEqual(tc, "code-change")
        self.assertEqual(skill, "implement-change")
        self.assertIn("security-review", extras)

    def test_es_anlamli_yazma_fiilleri_sozlukte(self):
        # P1: fiil listesi eksikti — "iyileştir" açık değişiklik emriydi.
        _tc, skill, _e, _x = self.pick("dashboard ekranını iyileştir")
        self.assertEqual(skill, "designing-interfaces")

    # --- incele.py P1 bulguları, 3. tur (PR #43) ---

    def test_gecmis_zaman_ve_sifat_fiil_emir_sayilmaz(self):
        # P1: -DI / -DIğ biçimleri emir sayılıyordu — "eklediğimiz"
        # tamamlanmış işi anlatır, yeni mutasyon talebi değildir.
        tc, skill, _e, _x = self.pick(
            "eklediğimiz auth kodunu güvenlik açısından incele")
        self.assertEqual(tc, "research")
        self.assertEqual(skill, "security-review")

    def test_belirsiz_niyette_tablo_otoritesi_korunur(self):
        # P1: tanınmayan fiil ("devreye al") varsayılan okumaya düşüp
        # zorunlu skill'i yutuyordu. Kapı yalnız POZİTİF okuma niyetinde
        # devreye girer; niyet belirsizse tetik tablosu karar verir.
        tc, skill, _e, _x = self.pick("login endpointini devreye al")
        self.assertEqual(tc, "code-change")
        self.assertEqual(skill, "implement-change")

    # --- incele.py P1 bulguları, 6. tur (PR #43) ---

    def test_hafif_fiil_okuma_adiyla_mutasyon_sayilmaz(self):
        # P1: "yap" bağlamdan bağımsız mutasyon sayılıyordu. Türkçede
        # "analiz yap" birleşik fiildir; anlamı taşıyan AD'dır, "yap"
        # yalnız yardımcıdır — istek okumadır.
        for prompt in ("login akışının güvenlik analizini yap",
                       "kod tabanının incelemesini yap",
                       "bağımlılıkların değerlendirmesini yapalım"):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "research")

    def test_hafif_fiil_citi_gercek_is_emrini_yutmaz(self):
        # Negatif kontrol: önündeki ad okuma adı değilse "yap" yazmadır.
        for prompt, beklenen in (
                ("API endpointine stres testi yap", "code-change"),
                ("raporda önerilen düzeltmeyi yap", "code-change"),
                ("login akışını yap", "code-change")):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, beklenen)

    # --- incele.py P1 bulguları, 5. tur (PR #43) ---

    def test_salt_okunur_turda_oneri_de_izin_sinirina_tabidir(self):
        # P1: salt-okunur sınıfa indirilen yazma kuralları "Ek skill"
        # olarak öneriliyordu — capability profili izin sınırıdır, öneri
        # de o sınıra tabidir; yoksa sınır tavsiyeye döner.
        for prompt in ("AurasAgents router, AurasPrime, kanıt kapıları ve "
                       "hafıza sistemini eleştirel incele",
                       "çekirdek profillerini gözden geçir"):
            with self.subTest(prompt=prompt):
                tc, _s, extras, _x = self.pick(prompt)
                self.assertEqual(tc, "research")
                disarida = [s for s in extras
                            if route.skill_izinli(s, ROOT)
                            and not route.sinifta_izinli(s, tc, ROOT)]
                self.assertFalse(disarida, f"profil dışı öneri: {disarida}")

    def test_edilgen_deyim_yazma_emri_sayilmaz(self):
        # P1: çok kelimeli deyim biçim aranmadan alt-dize eşleşiyordu —
        # "devreye alınması" edilgen ad, emir değil.
        tc, _s, _e, _x = self.pick(
            "auth endpointinin devreye alınması gereken notları raporla")
        self.assertEqual(tc, "research")

    def test_alintilanan_yazma_emri_niyet_sayilmaz(self):
        # P1: yalnızca ANILAN emir gerçek niyetten ayrılmıyordu. Tırnak
        # içi metin niyet taramasından çıkarılır (sınırlı ama mekanik
        # çare; cümleyi ANLAMAK bu katmanın işi değil — grilling
        # not_routed kararının aynı gerekçesi).
        tc, _s, _e, _x = self.pick(
            "router çıktısındaki 'kodu düzelt ve uygula' ifadesini incele")
        self.assertEqual(tc, "research")

    # --- incele.py P1 bulguları, 4. tur (PR #43) ---

    def test_ucuncu_sahis_simdiki_zaman_emir_sayilmaz(self):
        # P1: -Iyor/-AcAk kişi ayrımı olmadan emir sayılıyordu; kodu
        # TARİF eden cümle mutasyon olup salt-okunur denetime yazma
        # profili açıyordu (tehlikeli yön — bu PR'ın düzelttiği kusurun
        # ta kendisi).
        for prompt in ("bu servis geçici dosya oluşturuyor, "
                       "güvenlik açısından incele",
                       "yeni sürüm config'i değiştirecek, önce incele"):
            with self.subTest(prompt=prompt):
                tc, _s, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "research")

    def test_birinci_sahis_simdiki_zaman_is_beyanidir(self):
        # Kişi ayrımının diğer yüzü: "ekliyoruz" iş turudur, tarif değil.
        # Niyet katmanı doğrudan sınanır — uçtan uca yönlendirme ayrı bir
        # sınırla karışıyor: routing.yml tetik eşleşmesi ünlü düşmesini
        # tanımaz ("ekliyoruz" ≠ "ekle" öneki), bu PR'dan ESKİ bir kusur.
        for metin in ("bu servise cache ekliyoruz",
                      "auth akışını yeniden yazacağız",
                      "config'i güncelliyorum"):
            with self.subTest(metin=metin):
                self.assertTrue(niyet.mutasyon_niyeti(metin))
        # Tetik tablosunun görebildiği biçimde uçtan uca da doğrulanır.
        tc, _s, _e, _x = self.pick("auth akışını yeniden yazacağız")
        self.assertEqual(tc, "code-change")

    def test_deyim_yazma_emri_okuma_fiiliyle_yutulmaz(self):
        # P1: sözlük dışı yazma deyiminin ("devreye al") yanındaki okuma
        # fiili tüm isteği salt-okunur yapıyordu. Çok kelimeli yazma
        # deyimleri sözlüğe girdi.
        tc, skill, _e, _x = self.pick(
            "auth endpointini devreye al ve sonucu raporla")
        self.assertEqual(tc, "code-change")
        self.assertIsNotNone(skill)


if __name__ == "__main__":
    unittest.main()
