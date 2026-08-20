#!/usr/bin/env python3
"""Kuralsız /komut sınırları — izin sınırı, sınıf otoritesi, meta-skill.

test_route.py'den ayrıldı: dosya 400 satır sınırını aşmıştı (kalite
ratchet'i). Ayrım konu bazlı — burada TABLO değil ENVANTER kararları
sınanır: skill kurulu mu, hangi profilde izinli, sınıfını kim belirler.
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
class KuralsizKomutTest(unittest.TestCase):
    """Profil izin sınırıysa, profilde OLMAYAN skill zorunlu kılınamaz."""

    def kur(self, tmp, skill, profilde):
        os.makedirs(os.path.join(tmp, ".agents", "skills", skill))
        pd = os.path.join(tmp, ".agents", "capability-profiles")
        os.makedirs(pd)
        with open(os.path.join(pd, "research.yml"), "w", encoding="utf-8") as fh:
            fh.write("task_class: research\nskills:\n")
            if profilde:
                fh.write(f"  - {skill}\n")
            else:
                fh.write("  - baska-skill\n")

    def test_profilde_olmayan_kurulu_skill_zorunlu_kilinmaz(self):
        # Yalnız globalde duran üçüncü taraf skill, izin sınırı dışındadır:
        # sınıfını ve riskini uydurmak, sınırın kendisini uydurmaktır.
        with tempfile.TemporaryDirectory() as tmp:
            self.kur(tmp, "yabanci-skill", profilde=False)
            self.assertIsNone(route.kuralsiz_komut_kurali("yabanci-skill", tmp))

    def test_profildeki_skill_kural_uretir(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.kur(tmp, "tanimli-skill", profilde=True)
            kural = route.kuralsiz_komut_kurali("tanimli-skill", tmp)
            self.assertEqual(kural, {"skill": "tanimli-skill",
                                     "task_class": "research",
                                     "risk": "auto"})

    def test_profilsiz_projede_kanonik_profile_dusulur(self):
        """Bağlanmamış repo: profil yok ama /komut sınıfını kaybetmemeli.

        Önyükleme durumu — repoyu sisteme BAĞLAYAN skill, henüz .agents/'ı
        olmayan repoda çağrılır. Sınıf bulunamazsa dosya yazan iş salt-okunur
        profile düşer. Tablo için zaten kanoniğe düşülüyor (routing_path);
        profil için de aynı yol geçerli olmalı.
        """
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".agents", "skills",
                                     "designing-interfaces"))
            kural = route.kuralsiz_komut_kurali("designing-interfaces", tmp)
            self.assertEqual(kural, {"skill": "designing-interfaces",
                                     "task_class": "code-change",
                                     "risk": "approval"})

    def test_yerel_profil_kanonigi_ezer_kisitlama_korunur(self):
        """Projenin profili VARSA otorite odur — kanonik yedek devreye girmez.

        Yedeğin amacı önyükleme (profil YOK) durumudur. Profili olan ama bir
        skill'i bilinçli DIŞARIDA bırakan projede kanoniğe düşmek, yerel
        capability kısıtlamasını sessizce geçersiz kılar.
        """
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".agents", "skills",
                                     "implement-change"))
            pd = os.path.join(tmp, ".agents", "capability-profiles")
            os.makedirs(pd)
            with open(os.path.join(pd, "research.yml"), "w",
                      encoding="utf-8") as fh:
                fh.write("task_class: research\nskills:\n  - baska-skill\n")
            # implement-change kanonik code-change profilinde VAR ama bu
            # projede yok: yerel karar kazanmalı.
            self.assertIsNone(
                route.skill_task_class("implement-change", tmp))
            self.assertIsNone(
                route.kuralsiz_komut_kurali("implement-change", tmp))

    def test_profil_disi_gorev_skilli_yuklenmesi_istenmez(self):
        """Projenin dışarıda bıraktığı skill için "onu yükle" denmez.

        Sistemin YÖNETTİĞİ bir skill (.agents/skills altında var) profilde
        yoksa bu bilinçli dışlamadır. "Kullanıcı istedi, yükle" demek,
        kısıtlamayı tavsiyeye çevirir — sınır ancak reddedince sınırdır.
        """
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".agents", "skills", "yasak-skill"))
            pd = os.path.join(tmp, ".agents", "capability-profiles")
            os.makedirs(pd)
            with open(os.path.join(pd, "research.yml"), "w",
                      encoding="utf-8") as fh:
                fh.write("task_class: research\nskills:\n  - baska-skill\n")
            cfg = route.load_rules()
            context, _s = route.render("/yasak-skill bir şey yap", cfg,
                                       pdir=tmp)
            self.assertNotIn("onu yükle", context)
            self.assertIn("izin sınırı dışında", context)

    def test_yonetilmeyen_komut_yine_yuklenir(self):
        """Sistemin yönetmediği (ör. eklenti) skill'e karışılmaz.

        Profilde olmaması dışlama DEĞİL, kapsam dışılıktır: /dataviz gibi
        komutları reddetmek router'ı kullanıcının aracına karşı çalıştırırdı.
        """
        with tempfile.TemporaryDirectory() as tmp:
            pd = os.path.join(tmp, ".agents", "capability-profiles")
            os.makedirs(pd)
            with open(os.path.join(pd, "research.yml"), "w",
                      encoding="utf-8") as fh:
                fh.write("task_class: research\nskills:\n  - baska-skill\n")
            cfg = route.load_rules()
            context, _s = route.render("/dataviz grafik çiz", cfg, pdir=tmp)
            self.assertIn("onu yükle", context)

    def test_meta_skill_sinifi_kilitlemez(self):
        """Her profilde izinli skill, görev sınıfını KENDİ belirlemez.

        AurasPrime bir meta-skill: kendisi iş yapmaz, işi dağıtır. Sınıfı
        'research'e kilitlemek, devrettiği kod işini salt-okunur profile
        mahkûm eder. Her sınıfta izinli olmak "sınırsız" değil "sınıfı
        işten gelir" demektir.
        """
        self.assertIsNone(route.skill_task_class("aurasprime", ROOT))
        # Sınıf işin kendisinden gelir
        cfg = route.load_rules()
        tc, primary, _e, _h, _x = route.route(
            "/aurasprime kullanıcı endpointi ekle", cfg, ROOT)
        self.assertEqual(tc, "code-change")
        self.assertEqual((primary or {}).get("skill"), "aurasprime")
        self.assertEqual((primary or {}).get("risk"), "approval")

    def test_meta_skill_izin_siniri_disinda_sayilmaz(self):
        # Her profilde izinli olmak, "profilde yok" ile karıştırılmamalı.
        # `profil_disinda` SAHİBİNDEN çağrılır (bin/skill_kayit.py): 2026-08-16'da
        # route.py'den enjekte.py'ye taşındı ve route üzerinden erişim koptu —
        # test aracın yerine değil, sahibine bağlanmalı.
        import skill_kayit
        self.assertFalse(skill_kayit.profil_disinda("aurasprime", ROOT))
        self.assertIsNotNone(route.kuralsiz_komut_kurali("aurasprime", ROOT))


@pyyaml_gerekir
class OnSinifNihaiSinifTest(unittest.TestCase):
    """Router'ın sınıfı ÖN sınıftır; nihai sınıf diff'ten gelir (AGENTS.md).

    İnceleme bulgusu (PR #41): 'AurasPrime sınıfı devirden önce anahtar
    kelimeyle sabitleniyor.' Tasarım cevabı: sabitlemiyor, TAHMİN ediyor ve
    tahmin bağlayıcı değil — üç halka bunu kapatır: (1) hook çıktısı riski
    'ön risk' diye etiketler, (2) AGENTS.md 'nihai sınıf diff'ten' der,
    (3) incele.py merge kapısında riski diff yollarından yeniden hesaplar.
    Bu test o zinciri KIRILMAZ kılar: halkalardan biri koparsa (etiket
    kalkar, incele diff'e bakmaz olur) burada kırmızı görünür.
    """

    def test_hook_riski_on_risk_diye_etiketler(self):
        cfg = route.load_rules()
        context, _s = route.render("/aurasprime kullanıcı endpointi ekle",
                                   cfg, pdir=ROOT)
        self.assertIn("ön risk", context)

    def test_nihai_risk_diff_yollarindan_hesaplanir(self):
        spec = importlib.util.spec_from_file_location(
            "incele", os.path.join(ROOT, "bin", "incele.py"))
        incele = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(incele)
        # Router ne tahmin ederse etsin: bin/ dosyasına dokunan diff approval,
        # yalnız docs'a dokunan diff auto — otorite diff'tir.
        self.assertEqual(incele.risk_sinifi(["bin/route.py"]), "approval")
        self.assertEqual(incele.risk_sinifi(["docs/notlar.md"]), "auto")
