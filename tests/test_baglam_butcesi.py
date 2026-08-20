#!/usr/bin/env python3
"""Bağlam bütçesi bekçisi — her turda enjekte edilen metnin tavanı.

Neden ayrı bekçi: router'ın davranış sözleşmesi HER prompt'a girer, yani
maliyeti tur sayısıyla çarpılır. 2026-08-15 ölçümü: sabit iskele 1732
karakter (~600 token); 200 turluk bir oturumda yalnız iskele ~120K token.
Bu, kullanıcının gerçek işine ayrılmayan bağlamdır.

Kural tek cümle: enjekte edilen metin TALİMAT taşır, GEREKÇE taşımaz.
Gerekçenin yeri oturum başına bir kez yüklenen AGENTS.md ya da yalnız
gerektiğinde yüklenen skill dosyasıdır. Bir metin "neden böyle" anlatıyorsa
her turda ödenmemelidir.

Bekçi olmadan bu sınır kayar: her yeni davranış kuralı birkaç yüz karakter
ekler, kimse toplamı ölçmez ve altı ay sonra enjeksiyon prompt'un kendisinden
büyük olur. Tavanı yükseltmek bilinçli bir karardır — gerekçesi commit
mesajına yazılır (kalite ratchet'iyle aynı sözleşme, ADR-0004).
"""
import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortam import pyyaml_gerekir  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "davranis", os.path.join(ROOT, "bin", "davranis.py"))
davranis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(davranis)

_rspec = importlib.util.spec_from_file_location(
    "route", os.path.join(ROOT, "bin", "route.py"))
route = importlib.util.module_from_spec(_rspec)
_rspec.loader.exec_module(route)

# Sabit iskele tavanı: karşılama + sahip + itiraz + başlık + hafıza şablonu.
# 2026-08-15'te 1732'den indirildi; gerekçeler AGENTS.md'ye taşındı.
ISKELE_TAVANI = 900

# Tam enjeksiyon tavanı (hafıza kayıtları dâhil, iş emri turu).
ENJEKSIYON_TAVANI = 1600


class BaglamButcesiTest(unittest.TestCase):
    def test_sabit_iskele_tavani_asilmaz(self):
        """Her turda ödenen sabit metin tavanın altında kalmalı."""
        toplam = sum(len(m) for m in (
            davranis.KARSILAMA, davranis.GECMIS_YOK, davranis.SAHIP_VAR,
            davranis.ITIRAZ, davranis.BASLIK))
        self.assertLessEqual(
            toplam, ISKELE_TAVANI,
            f"sabit iskele {toplam} karakter (tavan {ISKELE_TAVANI}). "
            "Gerekçe metnini AGENTS.md'ye ya da skill'e taşı; tavanı "
            "yükseltmek bilinçli karardır ve gerekçesi commit'e yazılır.")

    def test_itiraz_yalniz_yazma_riskinde_odenir(self):
        """Sohbet/araştırma turunda itiraz metni enjekte EDİLMEZ."""
        okuma = "\n".join(davranis.sozlesme("research-analyst", "research",
                                            "auto"))
        yazma = "\n".join(davranis.sozlesme("backend-engineer", "code-change",
                                            "approval"))
        self.assertNotIn("İTİRAZ", okuma.upper())
        self.assertIn("İTİRAZ", yazma.upper())

    @pyyaml_gerekir
    def test_tam_enjeksiyon_tavani_asilmaz(self):
        """İş emri turunun tam bağlamı (hafıza dâhil) tavanın altında."""
        cfg = route.load_rules()
        context, _s = route.render("login endpointine rate limit ekle", cfg,
                                   pdir=ROOT)
        self.assertLessEqual(
            len(context), ENJEKSIYON_TAVANI,
            f"enjeksiyon {len(context)} karakter (tavan {ENJEKSIYON_TAVANI}).")

    def test_iskele_talimat_tasir_gerekce_tasimaz(self):
        """Gerekçe işaretleri ('çünkü', 'yoksa …-ordu') iskelede olmamalı.

        Kaba ama yönü doğru sinyal: bu kalıplar bir metnin NEDEN'i
        anlattığını gösterir ve neden her turda ödenmez.
        """
        iskele = " ".join((davranis.KARSILAMA, davranis.SAHIP_VAR,
                           davranis.ITIRAZ, davranis.BASLIK)).lower()
        for isaret in ("çünkü", "denetleyemez", "bu yüzden"):
            self.assertNotIn(
                isaret, iskele,
                f"iskelede gerekçe metni var ('{isaret}') — AGENTS.md'ye taşı")


if __name__ == "__main__":
    unittest.main()
