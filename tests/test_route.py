#!/usr/bin/env python3
"""bin/route.py yönlendirme testleri — istek → beklenen skill eşlemesi."""
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


# Sınıfın TAMAMI yönlendirme tablosunu okur; tablo yaml'dır. PyYAML yoksa
# setUpClass çökerdi ve sınıfın tüm testleri süitten YOK OLURDU (tek hata
# satırı, sayıda 26 test eksik). Atlama sayıyı korur, gerekçeyi gösterir.
@pyyaml_gerekir
class RouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = route.load_rules()

    def pick(self, prompt):
        task_class, primary, extras, _hits, explicit = route.route(
            prompt, self.cfg)
        return task_class, (primary or {}).get("skill"), extras, explicit

    # --- soru turu vs iş emri (2026-08-07 bulgusu) ---
    # Bir oturumda 12+ tur yanlış sınıflandı: soru sorulduğunda router
    # `code-change` + `approval` ilan edip zorunlu skill dayattı. Türkçe
    # önek eşleşmesi DOĞRU çalışıyordu ("yapmalıyız" → "yap" aynı fiil);
    # kusur tur TİPİNİN okunmamasıydı. Soru ≠ iş emri.

    def test_soru_turu_zorunlu_skill_dayatmaz(self):
        for prompt in ("bizim hafıza tarafı başarılı mı?",
                       "sonuç anlayacağım dilde ne yapmalıyız?",
                       "gerçekten dürüst önerin var mı?",
                       "kodlamada nasıl bir standartta teslim ediyorsun?",
                       "sence bu sistem iyi mi"):
            with self.subTest(prompt=prompt):
                tc, skill, _e, _x = self.pick(prompt)
                self.assertIsNone(
                    skill, f"soru turuna zorunlu skill dayatıldı: {skill}")
                self.assertEqual(tc, "research", "soru turu salt-okunur profil almalı")

    def test_is_emri_soru_kelimesi_tasisa_bile_yonlendirilir(self):
        # "neden"/"nasıl" geçen ama EMİR olan turlar iş olarak kalmalı.
        for prompt in ("actions'a bak neden koşmadı",
                       "bu bug neden oluyor bul ve düzelt"):
            with self.subTest(prompt=prompt):
                _tc, skill, _e, _x = self.pick(prompt)
                self.assertIsNotNone(skill, "emir turu skill'siz kaldı")

    def test_acik_slash_komut_soruda_bile_kazanir(self):
        # Kullanıcı açıkça /auras dediyse soru biçimi bunu ezmemeli.
        _tc, skill, _e, explicit = self.pick("/auras bunu bağlar mısın?")
        self.assertEqual(explicit, "auras")
        self.assertEqual(skill, "auras")


    def test_kod_istegi_implement_change(self):
        for prompt in ("kullanıcı listesi endpoint'i ekle",
                       "şu bug'ı düzelt",
                       "bu servisi refactor edelim"):
            with self.subTest(prompt=prompt):
                tc, skill, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "code-change")
                self.assertEqual(skill, "implement-change")

    def test_arastirma_istegi_research(self):
        for prompt in ("bu metrik nerede hesaplanıyor",
                       "iki yaklaşımı karşılaştır",
                       "cache stratejilerini araştır"):
            with self.subTest(prompt=prompt):
                tc, skill, _e, _x = self.pick(prompt)
                self.assertEqual(tc, "research")
                self.assertEqual(skill, "research-with-evidence")

    def test_guvenlik_ozgul_kural_geneli_yener(self):
        # "incele" research tetiği, "güvenlik/auth" security tetiği: özgül kazanır
        _tc, skill, _e, _x = self.pick("login akışını güvenlik açısından incele")
        self.assertEqual(skill, "security-review")

    def test_risk_yuzeyi_ek_skill_ekler(self):
        _tc, skill, extras, _x = self.pick(
            "ödeme servisine yeni alan ekle ve migration yaz")
        self.assertEqual(skill, "implement-change")
        self.assertIn("security-review", extras)

    def test_kernel_isi_kernel_work(self):
        _tc, skill, _e, _x = self.pick("validate.py'ye yeni bekçi testi ekle")
        self.assertEqual(skill, "kernel-work")

    def test_tasarim_istegi(self):
        _tc, skill, _e, _x = self.pick("dashboard ekranını premium tasarla")
        self.assertEqual(skill, "designing-interfaces")

    def test_grilling_dogal_dille_yonlendirilmez(self):
        """grilling YALNIZ /grilling ile çağrılır — doğal dil tetiği yok.

        Denendi ve kaldırıldı (PR #39): anahtar kelime katmanı cümleyi
        anlamadığı için ret ("sorguya çekme"), alıntı, yük testi ve yemek
        anlamları yanlış-pozitif üretti. Yanlış açılan sorgu oturumunun
        bedeli, kaçırmanın bedelinden yüksek.
        """
        for istem in ("beni sorguya çek", "planımı stres testine sok",
                      "beni grill'le", "beni sorguya çeker misin?"):
            _tc, skill, extras, _x = self.pick(istem)
            self.assertNotEqual(skill, "grilling", istem)
            self.assertNotIn("grilling", extras, istem)

    def test_grilling_acik_komutla_cagrilir(self):
        _tc, _skill, _e, explicit = self.pick("/grilling planı netleştirelim")
        self.assertEqual(explicit, "grilling")

    def test_profil_sinifi_okunabiliyor(self):
        """skill_task_class GERÇEKTEN çalışıyor mu (yalnız None dönmüyor mu).

        Yönlendirme testi bunu kanıtlamaz: tetik eşleşmesi aynı sınıfı
        tesadüfen üretebilir ve bozuk profil okuması fark edilmez.
        """
        self.assertEqual(route.skill_task_class("grilling", ROOT), "research")
        self.assertEqual(route.skill_task_class("implement-change", ROOT),
                         "code-change")
        self.assertIsNone(route.skill_task_class("boyle-bir-skill-yok", ROOT))

    def test_sinif_profil_ALFABESINE_bagli_degil(self):
        """Sınıf yazarın beyanından gelir; dosya adı sırasından DEĞİL.

        ÖLÇÜM 2026-08-16 — dördüncü profil (`design.yml`) eklenince İKİ sessiz
        kayma oldu, o profillere hiç dokunulmadan: `research-with-evidence`
        incident → design, `security-review` None → code-change. Sebep,
        sınıfın `sorted(os.listdir())` sırasının İLK elemanından türetilmesiydi
        ("design" < "incident"). Aynı şans `implement-change`i doğru
        gösteriyordu ("code-change" < "incident") — yani test yeşildi ama
        mekanizma yanlıştı.

        Bu bekçi eşlemeyi routing.yml'e sabitler: yeni bir profil dosyası
        eklemek hiçbir skill'in sınıfını değiştiremez.
        """
        for skill, beklenen in (("implement-change", "code-change"),
                                ("research-with-evidence", "research"),
                                ("designing-interfaces", "code-change"),
                                ("security-review", "code-change"),
                                ("kernel-work", "code-change")):
            with self.subTest(skill=skill):
                self.assertEqual(route.skill_task_class(skill, ROOT), beklenen,
                                 f"{skill}: sınıf routing.yml beyanına uymuyor")

    def test_kuralsiz_skill_tek_profildeyse_sinifini_alir(self):
        """routing.yml'de kuralı olmayan skill: profil tek ise sınıf odur."""
        self.assertEqual(route.skill_task_class("grilling", ROOT), "research")

    def test_cok_profilli_kuralsiz_skill_sinifsizdir(self):
        """aurasprime her profilde: sınıfı işten gelir, uydurulmaz."""
        self.assertIsNone(route.skill_task_class("aurasprime", ROOT))

    def test_profil_sinifi_kelime_puanlamasini_yener(self):
        """Otorite profildir: kelimeler başka sınıf söylese bile.

        "/grilling kodu düzelt ve uygula" isteminde tetikler code-change
        diyor; profil research diyor. Komutun sınıfı izin sınırından gelir,
        yoksa kullanıcı /komutla yazma yetkisi açabilirdi.
        """
        tc, _s, _e, explicit = self.pick("/grilling kodu düzelt ve uygula")
        self.assertEqual((tc, explicit), ("research", "grilling"))

    def test_kuralsiz_komut_risk_metadatasini_kaybetmez(self):
        """Yazma sınıfındaki /komut, risk sınıfını da taşımalı.

        Aynı işi yapan iki komuttan birinin approval diğerinin sessizce
        'auto' sayılması, risk politikasını komut seçimine bağlardı.
        (Vaka 2026-08-16'da `project-onboarding`den `auras`a taşındı:
        iki onboarding skill'i tek akışta birleştirildi.)
        """
        tc, skill, _e, _x = self.pick("/auras")
        self.assertEqual(tc, "code-change")
        self.assertEqual(skill, "auras")

    def test_acik_komut_tetik_tasiyan_metinde_de_kazanir(self):
        """Kurallı olmayan skill'in /komutu, anahtar kelimeye yenilmez.

        "/grilling ... nasıl kurgulayacağımı bilmiyorum" isteminde "nasıl"
        research tetiğidir. Kullanıcı komutla seçimini yapmışken başka bir
        skill'i ZORUNLU kılmak, açık iradeyi anahtar kelimeyle ezmektir.
        """
        _tc, skill, _e, explicit = self.pick(
            "/grilling yeni bildirim sistemini nasıl kurgulayacağımı bilmiyorum")
        self.assertEqual(explicit, "grilling")
        # Zorunlu kılınan skill, kullanıcının istediği skill olmalı
        self.assertEqual(skill, "grilling")

    def test_yuk_testi_kod_isidir(self):
        _tc, skill, _e, _x = self.pick("API endpointine stres testi yap")
        self.assertEqual(skill, "implement-change")

    def test_acik_slash_komut_her_seyi_yener(self):
        tc, skill, _e, explicit = self.pick("/auras bu projeyi bağla")
        self.assertEqual(explicit, "auras")
        self.assertEqual(skill, "auras")
        self.assertEqual(tc, "code-change")

    def test_eslesmezse_fallback_ve_primary_yok(self):
        tc, skill, _e, _x = self.pick("merhaba")
        self.assertIsNone(skill)
        self.assertEqual(tc, "research")

    def test_turkce_ek_ve_buyuk_harf(self):
        _tc, skill, _e, _x = self.pick("BU SERVİSE CACHE EKLEYELİM")
        self.assertEqual(skill, "implement-change")

    def test_hook_ciktisi_gecerli_json_sozlesmesi(self):
        context, summary = route.render("cache ekle", self.cfg)
        self.assertIn("implement-change", context)
        self.assertIn("router", summary)

    def test_proje_tablosu_kanonigi_yener(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, ".agents"))
            local = os.path.join(td, ".agents", "routing.yml")
            open(local, "w").close()
            path, is_local = route.routing_path(td)
            self.assertEqual(path, local)
            self.assertTrue(is_local)

    def test_tablosuz_projede_kanonige_duser(self):
        with tempfile.TemporaryDirectory() as td:
            path, is_local = route.routing_path(td)
            self.assertEqual(path, route.CANONICAL)
            self.assertFalse(is_local)

    def test_global_yedek_proje_hooku_varsa_cekilir(self):
        # AurasAgents'ın kendisi router hook'unu kaydeder → global yedek susar
        os.environ["CLAUDE_PROJECT_DIR"] = ROOT
        try:
            self.assertTrue(route.project_registers_router(ROOT))
            self.assertEqual(route.main(["--global-fallback"]), 0)
        finally:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def test_kurulu_olmayan_skill_uyarisi(self):
        with tempfile.TemporaryDirectory() as td:
            context, _s = route.render("cache ekle", self.cfg, pdir=td,
                                       table_is_local=False)
            self.assertIn("kurulu değil", context)
            self.assertIn("kanonik", context)

    def test_kurulu_skill_uyari_uretmez(self):
        context, _s = route.render("cache ekle", self.cfg, pdir=ROOT)
        self.assertNotIn("kurulu değil", context)

    def test_gorunurluk_basligi_dayatilir(self):
        # Kullanıcı yazışmada ne olduğunu görmeli — bu bir temenni değil,
        # her turda enjekte edilen zorunlu biçim.
        # Ölçüt biçimin İŞARETLERİdir, giriş cümlesi değil (2026-08-15):
        # "Cevabına" dizesini aramak metni kısaltmayı testi kırmakla
        # cezalandırıyordu. Sözleşme üç satırın varlığıdır.
        context, _s = route.render("cache ekle", self.cfg, pdir=ROOT)
        self.assertIn("🧭", context)     # skill satırı
        self.assertIn("👤", context)     # sahip satırı
        self.assertIn("🔧", context)     # ne yapıldı satırı
        self.assertIn("Sınıf:", context)
        self.assertIn("Risk:", context)

    def test_baslik_sohbet_turunda_da_istenir(self):
        context, _s = route.render("merhaba nasılsın", self.cfg, pdir=ROOT)
        self.assertIn("🧭", context)

    def test_disiplin_sahibi_secilir(self):
        """Analiz 'bu iş kimin işi' sorusunu cevaplamalı — tek sahip."""
        vakalar = (
            ("login ekranının butonları bozuk görünüyor", "frontend-engineer"),
            ("kullanıcı endpoint'ine yetki kontrolü ekle", "backend-engineer"),
            ("bu sorgu çok yavaş, index önerisi lazım", "database-engineer"),
            ("monolit mi mikroservis mi olmalı", "software-architect"),
            ("kullanıcı bu akışta hedefe varamıyor", "ux-designer"),
            ("docker compose deploy pipeline'ı kur", "devops-engineer"),
            ("model drift'i nasıl izleyelim", "ml-ai-engineer"),
        )
        for prompt, beklenen in vakalar:
            with self.subTest(prompt=prompt):
                self.assertEqual(route.sahip(prompt, self.cfg), beklenen)

    def test_tek_sahip_dondurur_zincir_degil(self):
        # Rol tiyatrosu yasağı: birden çok disiplin eşleşse de TEK sahip döner
        sahip = route.sahip("frontend butonu backend endpoint'i sorgu index",
                            self.cfg)
        self.assertIsInstance(sahip, str)

    def test_sahip_baglama_enjekte_edilir(self):
        context, _s = route.render("bu sorguyu hızlandır", self.cfg, pdir=ROOT)
        self.assertIn("👤", context)
        self.assertIn("database-engineer", context)

    def test_baslikta_sahip_satiri_var(self):
        context, _s = route.render("bu sorguyu hızlandır", self.cfg, pdir=ROOT)
        self.assertIn("👤 Sahip: database-engineer", context)

    def test_itiraz_yukumlulugu_enjekte_edilir(self):
        context, _s = route.render("cache ekle", self.cfg, pdir=ROOT)
        self.assertIn("İTİRAZ", context.upper())

    def test_bos_istek_ciktisiz(self):
        # main() stdin okur; boş istek yönlendirme üretmemeli
        self.assertEqual(route.route("", self.cfg)[1], None)

    def test_aurasprime_her_iste_karsilar(self):
        """Karşılama varsayılan: iş isteğinde AurasPrime devrede olmalı.

        Skill'in kendi pozitif eval girdisi ona ulaşmıyorsa karşılama
        katmanı yok demektir — kullanıcının /aurasprime yazması gerekirdi.
        """
        context, _s = route.render(
            "müşteriler faturayı geç görüyor, bir şeyler yapalım",
            self.cfg, pdir=ROOT)
        self.assertIn("AurasPrime", context)

    def test_acik_komutta_karsilama_yapilmaz(self):
        # Kullanıcı seçimini yapmışsa araya girilmez
        context, _s = route.render("/grilling planı netleştirelim",
                                   self.cfg, pdir=ROOT)
        self.assertNotIn("AurasPrime", context)

    def test_guvenlik_arastirmasinda_risk_yuzeyi_kaybolmaz(self):
        """Fiiller birincil skill'i seçer; alan kelimesi risk yüzeyini EKLER.

        İnceleme bulgusu: 'güvenlik durumunu incele ve karşılaştır' iki
        araştırma fiiliyle research'e gidiyor ve güvenlik bağlamı düşüyordu.
        Çözüm puan çarpımı değil (denendi, salınım üretti) — always_add:
        'güvenlik' risk-yüzeyi kelimesidir, birincil ne olursa olsun
        security-review daima eklenir.
        """
        _tc, skill, extras, _x = self.pick("güvenlik durumunu incele ve karşılaştır")
        self.assertEqual(skill, "research-with-evidence")
        self.assertIn("security-review", extras)


# Kuralsız /komut testleri tests/test_route_komut.py'de, olay (incident)
# eskalasyonu tests/test_route_olay.py'de (dosya-boyutu eşiği, 2026-08-12)
# — burada yalnız yönlendirme tablosu vakaları yaşar.

if __name__ == "__main__":
    unittest.main()
