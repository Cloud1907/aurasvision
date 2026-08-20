#!/usr/bin/env python3
"""Salt-okunur sınıf TEK değildir — niyet kapısı bunu bilmeli.

ÖLÇÜM 2026-08-16 (ADR-0005): `design` sınıfı açıldı; `tools.filesystem:
read-only` taşıyor, yani `research` gibi yazmayan bir sınıf. Ama `niyet.py`
`"research"`i TEK salt-okunur sınıf sayıyordu ve okuma niyetli HER kuralı
oraya düşürüyordu. Canlı deneme: `lighthouse çalıştır` kuralı doğru eşleşti,
sınıf `design` → `research` indi ve kural `design` profilindeki
chrome-devtools'u kaybetti. Yani çalışmayan ama çalışır görünen yönlendirme —
o yüzden design kuralı hiç yayınlanmadı, sebebi `routing.yml`'e yazıldı.

BU BEKÇİNİN ASIL İŞİ GEVŞEMEYİ ENGELLEMEK. Düzeltme iki yönlü olabilirdi ve
biri YANLIŞTI:
  · doğru  → salt-okunur sınıftaki kural KENDİ sınıfını korur,
  · yanlış → düşürme hedefini `design` yapmak; o zaman yazma sınıfındaki bir
    kural, salt-okunur olsun diye Figma/Canva/Nim taşıyan bir profile
    "indirilirdi" — yani indirme, yetki GENİŞLETMESİ olurdu.
Aşağıdaki `test_yazma_kurali_EN_KISITLI_sinifa_iner` tam olarak bunu tutar.
"""
import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(ad):
    spec = importlib.util.spec_from_file_location(
        ad, os.path.join(ROOT, "bin", f"{ad}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


niyet = _load("niyet")
skill_kayit = _load("skill_kayit")

SALT = ("research", "design")


def _kural(sinif, skill="research-with-evidence", **ek):
    return dict({"skill": skill, "task_class": sinif}, **ek)


class SaltOkunurSiniflarTest(unittest.TestCase):
    """Kaynak profilin KENDİ beyanıdır (`tools.filesystem`), sabit liste değil."""

    def test_profil_beyanindan_okunur(self):
        kume = skill_kayit.salt_okunur_siniflar(ROOT)
        self.assertIn("research", kume)
        self.assertIn("design", kume, "design profili read-only ama sayılmadı")
        self.assertNotIn("code-change", kume)
        self.assertNotIn("incident", kume)

    def test_profil_okunamazsa_research_e_duser(self):
        """Ölçüm yoksa EN KISITLI varsayım: yalnız research salt-okunurdur."""
        with tempfile.TemporaryDirectory() as td:
            # Profil dizini yok → kanoniğe düşer; kanonik de yoksa varsayılan.
            self.assertIn("research", skill_kayit.salt_okunur_siniflar(td))

    def test_donus_degistirilemez(self):
        """Çağıran kümeyi kirletemesin (kapı verisi paylaşılıyor)."""
        self.assertIsInstance(skill_kayit.salt_okunur_siniflar(ROOT), frozenset)


class OkumaSinifiTest(unittest.TestCase):
    """Düşürme YÖNÜ: kısıtlar, genişletmez."""

    def test_salt_okunur_kural_KENDI_sinifini_korur(self):
        k = niyet._okuma_sinifi(_kural("design"), SALT)
        self.assertEqual(k["task_class"], "design",
                         "design salt-okunur; research'e indirmek aracını alır")

    def test_research_kurali_aynen_kalir(self):
        self.assertEqual(
            niyet._okuma_sinifi(_kural("research"), SALT)["task_class"],
            "research")

    def test_yazma_kurali_EN_KISITLI_sinifa_iner(self):
        """`code-change` → `research`; ASLA `design`.

        design salt-okunur AMA Figma/Canva/Nim taşır. Yazma kuralını oraya
        indirmek, kısıtlama adı altında dış SaaS yetkisi vermek olurdu.
        """
        for sinif in ("code-change", "incident"):
            with self.subTest(sinif=sinif):
                k = niyet._okuma_sinifi(_kural(sinif, skill="implement-change"),
                                        SALT)
                self.assertEqual(k["task_class"], "research")

    def test_kaynak_kural_bozulmaz(self):
        """Kopya döner — cfg paylaşılan nesnedir."""
        asil = _kural("code-change")
        niyet._okuma_sinifi(asil, SALT)
        self.assertEqual(asil["task_class"], "code-change")


class KuralNiyetiTest(unittest.TestCase):
    def test_salt_okunur_sinif_okuma_niyetidir(self):
        self.assertEqual(niyet.kural_niyeti(_kural("design"), SALT), "read")
        self.assertEqual(niyet.kural_niyeti(_kural("research"), SALT), "read")

    def test_yazma_sinifi_yazma_niyetidir(self):
        self.assertEqual(niyet.kural_niyeti(_kural("code-change"), SALT),
                         "write")

    def test_intent_alani_hala_ezer(self):
        """Tablo `intent` ile ezebilir (security-review: denetim okur)."""
        self.assertEqual(
            niyet.kural_niyeti(_kural("code-change", intent="read"), SALT),
            "read")

    def test_argumansiz_cagri_eski_davranisi_korur(self):
        """Geriye uyum: küme verilmezse yalnız research salt-okunur sayılır."""
        self.assertEqual(niyet.kural_niyeti(_kural("design")), "write")
        self.assertEqual(niyet.kural_niyeti(_kural("research")), "read")


class KapiUctanUcaTest(unittest.TestCase):
    """Belirsiz niyette design kuralı sınıfını korumalı."""

    def test_belirsizde_design_kurali_research_e_dusmez(self):
        scored = [(3, 2, _kural("design"), ["lighthouse"])]
        sonuc, _ek = niyet.niyet_kapisi("lighthouse", scored, [], SALT)
        self.assertEqual(sonuc[0][2]["task_class"], "design")

    def test_belirsizde_yazma_kurali_research_e_iner(self):
        scored = [(3, 2, _kural("code-change", skill="implement-change"), ["x"])]
        sonuc, _ek = niyet.niyet_kapisi("x", scored, [], SALT)
        self.assertEqual(sonuc[0][2]["task_class"], "research")


if __name__ == "__main__":
    unittest.main()
