#!/usr/bin/env python3
"""Router eval corpus'unu KOŞAR — tetikleme doğruluğu ölçülen bir sayı olur.

AGENTS.md skill yayın koşulu üç şart sayıyor: eval + routing tetiği + profil
kaydı. İkisi mekanizmaya bağlıydı, `eval` PROZAYDI: `.agents/skills/*/eval/
cases.md` dosyalarını hiçbir kapı koşmuyordu (`git grep "eval/cases" -- bin
.github` yalnız bir gitleaks yorumu buluyordu). Ölçülmeyen kural, kuralın
kendisi hakkında hiçbir şey söylemez.

Ölçüm (2026-08-15, `.agents/runtime/events.jsonl`, 210 tur): zorunlu skill
üretilen 90 turun 9'unda skill yüklendi (%10), 67'sinde sessizce atlandı.
Bu dosya o ölçümün "yönlendirme doğru muydu" yarısını kalıcı hâle getirir.

Vaka eklemek serbesttir ve teşvik edilir: ölçülen her yanlış yönlendirme
buraya kalıcı vaka olarak girer.
"""
import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortam import pyyaml_gerekir  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, ".agents", "routing-eval.yml")

_spec = importlib.util.spec_from_file_location(
    "route", os.path.join(ROOT, "bin", "route.py"))
route = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(route)


def _vakalar():
    import yaml
    with open(CORPUS, encoding="utf-8") as fh:
        return (yaml.safe_load(fh) or {}).get("vakalar") or []


@pyyaml_gerekir
class RoutingEvalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = route.load_rules()
        cls.vakalar = _vakalar()

    def test_corpus_bos_degil(self):
        self.assertGreaterEqual(
            len(self.vakalar), 25,
            "eval corpus'u anlamlı kapsam için en az 25 vaka taşımalı")

    def test_her_vaka_gerekce_tasir(self):
        """Gerekçesiz vaka, niye orada olduğu unutulan vakadır."""
        for v in self.vakalar:
            self.assertTrue((v.get("neden") or "").strip(),
                            f"vaka gerekçesiz: {v.get('istek')!r}")

    def test_vakalar_beklenen_yonlendirmeyi_uretir(self):
        hatalar = []
        for v in self.vakalar:
            istek = v["istek"]
            sinif, primary, extras, _hits, explicit = route.route(
                istek, self.cfg, ROOT)
            skill = (primary or {}).get("skill")
            if sinif != v["sinif"]:
                hatalar.append(f"{istek[:48]!r}: sınıf {sinif} "
                               f"≠ {v['sinif']}  ({v['neden'][:60]})")
            if skill != v.get("skill"):
                hatalar.append(f"{istek[:48]!r}: skill {skill} "
                               f"≠ {v.get('skill')}  ({v['neden'][:60]})")
            if v.get("ek") and v["ek"] not in extras:
                hatalar.append(f"{istek[:48]!r}: ek skill {v['ek']} yok "
                               f"(gelen: {extras})")
            if v.get("komut") and explicit != v["komut"]:
                hatalar.append(f"{istek[:48]!r}: komut {explicit} "
                               f"≠ {v['komut']}")
        self.assertEqual(hatalar, [], "\n  " + "\n  ".join(hatalar))

    def test_guvenlik_yanlis_negatifi_yok(self):
        """Güvenlik yüzeyine dokunan hiçbir vaka security-review'suz kalmamalı.

        Bu ölçüt AYRI: sınıf/skill hatası gürültüdür, güvenlik false-negative'i
        açıktır. Eşik SIFIR.
        """
        kacan = []
        for v in self.vakalar:
            if v.get("ek") != "security-review":
                continue
            _s, primary, extras, _h, _e = route.route(v["istek"], self.cfg, ROOT)
            secilen = {(primary or {}).get("skill"), *extras}
            if "security-review" not in secilen:
                kacan.append(v["istek"][:60])
        self.assertEqual(kacan, [], f"güvenlik false-negative: {kacan}")

    def test_dil_dengesi(self):
        """Corpus tek dilli olamaz — cross-engine iddiası İngilizce ister."""
        ingilizce = [v for v in self.vakalar
                     if any(k in v["istek"].lower()
                            for k in ("review", "add ", "where", "audit",
                                      "refactor"))]
        self.assertGreaterEqual(len(ingilizce), 4,
                                "corpus'ta yeterli İngilizce vaka yok")


if __name__ == "__main__":
    unittest.main()
