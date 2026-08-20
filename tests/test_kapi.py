#!/usr/bin/env python3
"""Muhatap kapısı testleri — kanıtsız bitişi gerçekten kesiyor mu."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "bin", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kapi = _load("kapi")


def olay(kind, **kw):
    d = {"kind": kind}
    d.update(kw)
    return d


class KapiTest(unittest.TestCase):
    def bulgular(self, olaylar, satir=0, dogrulayici=None):
        b, _sig = kapi.degerlendir(olaylar, satir, dogrulayici)
        return {(tip, baslik) for tip, baslik, _ayrinti in b}

    # --- skill doğrulayıcılarının kapıya bağlanması ---

    def test_test_once_bozulduysa_bloklar(self):
        b = self.bulgular(
            [olay("edit", file="src/app.py"),
             olay("test", cmd="python3 -m unittest", ok=True)],
            dogrulayici={"test_first": (1, "1 kaynak degisti, 0 test")})
        self.assertIn(("BLOK", "test-önce bozuldu"), b)

    def test_test_once_temizse_gecer(self):
        b = self.bulgular(
            [olay("edit", file="src/app.py"),
             olay("test", cmd="python3 -m unittest", ok=True)],
            dogrulayici={"test_first": (0, "temiz")})
        self.assertEqual(b, set())

    def test_dogrulayici_yoksa_kapi_kilitlenmez(self):
        # Bağlanmamış projede doğrulayıcı bulunmaz → None; kapı geçmeli
        b = self.bulgular(
            [olay("edit", file="src/app.py"),
             olay("test", cmd="unittest", ok=True)],
            dogrulayici={"test_first": None})
        self.assertEqual(b, set())

    def test_dokuman_isinde_test_once_calismaz(self):
        # Kaynak yoksa test-önce bulgusu üretilmemeli
        b = self.bulgular([olay("edit", file="docs/rapor.md")],
                          dogrulayici={"test_first": (1, "x")})
        self.assertEqual(b, set())

    def test_zayif_kaynakli_rapor_uyarir_bloklamaz(self):
        b = self.bulgular(
            [olay("edit", file=".agents/reports/2026-08-05-x.md")],
            dogrulayici={"kaynak": [(".agents/reports/2026-08-05-x.md",
                                     (1, "kaynaksiz oran %40"))]})
        self.assertIn(("UYARI", "rapor kaynak sinyali zayıf"), b)
        self.assertFalse([x for x in b if x[0] == "BLOK"])

    def test_dogrulayici_secimi_dosyaya_gore(self):
        # Kaynak değişmediyse test_first koşulmamalı (gereksiz alt süreç yok)
        self.assertEqual(kapi.dogrulayici_sonuclari(["docs/a.md"]), {})
        self.assertIn("test_first", kapi.dogrulayici_sonuclari(["src/a.py"]))

    def test_ayni_rapor_bir_kez_denetlenir(self):
        # Aynı dosya turda N kez düzenlenince kaynak denetimi N kez koşuyor
        # ve kapı aynı uyarıyı N kez basıyordu (2026-08-06 gürültü bulgusu).
        rapor = ".agents/reports/2026-08-06-x.md"
        sonuc = kapi.dogrulayici_sonuclari([rapor, rapor, rapor])
        self.assertEqual(len(sonuc.get("kaynak", [])), 1,
                         "aynı rapor birden çok kez denetlendi")

    def test_farkli_raporlar_ayri_denetlenir(self):
        sonuc = kapi.dogrulayici_sonuclari(
            [".agents/reports/a.md", ".agents/reports/b.md"])
        self.assertEqual(len(sonuc.get("kaynak", [])), 2)

    def test_duzenlenen_dosyalar_bu_turdan(self):
        olaylar = [olay("edit", file="eski.py"), olay("stop"),
                   olay("edit", file="yeni.py")]
        self.assertEqual(kapi.duzenlenen_dosyalar(olaylar), ["yeni.py"])

    def test_kaynak_degisti_test_yok_bloklar(self):
        b = self.bulgular([olay("edit", file="src/app.py")])
        self.assertIn(("BLOK", "test kanıtı yok"), b)

    def test_test_son_editten_once_kostuysa_bloklar(self):
        b = self.bulgular([
            olay("test", cmd="unittest", ok=True),
            olay("edit", file="src/app.py"),      # testten SONRA düzenlendi
        ])
        self.assertIn(("BLOK", "test kanıtı yok"), b)

    def test_test_son_editten_sonra_gectiyse_temiz(self):
        b = self.bulgular([
            olay("edit", file="src/app.py"),
            olay("test", cmd="python3 -m unittest", ok=True),
        ])
        self.assertEqual(b, set())

    def test_testler_kirmiziysa_bloklar(self):
        b = self.bulgular([
            olay("edit", file="src/app.py"),
            olay("test", cmd="unittest", ok=False),
        ])
        self.assertIn(("BLOK", "testler kırmızı"), b)

    def test_belirsiz_sonuc_uyarir_bloklamaz(self):
        b = self.bulgular([
            olay("edit", file="src/app.py"),
            olay("test", cmd="unittest", ok=None),
        ])
        self.assertIn(("UYARI", "test sonucu belirsiz"), b)
        self.assertFalse([x for x in b if x[0] == "BLOK"])

    def test_dokuman_degisikligi_test_istemez(self):
        b = self.bulgular([olay("edit", file="docs/rapor.md")])
        self.assertEqual(b, set())

    def test_test_dosyasi_tek_basina_kaynak_sayilmaz(self):
        b = self.bulgular([olay("edit", file="tests/test_app.py"),
                           olay("test", cmd="unittest", ok=True)])
        self.assertEqual(b, set())

    def test_ui_degisti_tiklama_yoksa_bloklar(self):
        b = self.bulgular([
            olay("edit", file="web/components/Login.tsx"),
            olay("test", cmd="npx vitest run", ok=True),   # birim testi YETMEZ
        ])
        self.assertIn(("BLOK", "tıklama kanıtı yok"), b)

    def test_tarayici_etkilesimi_tiklama_kaniti_sayilir(self):
        b = self.bulgular([
            olay("edit", file="web/components/Login.tsx"),
            olay("test", cmd="npx vitest run", ok=True),
            olay("ui", cmd="mcp__chrome-devtools__click"),
        ])
        self.assertNotIn(("BLOK", "tıklama kanıtı yok"), b)

    def test_e2e_komutu_tiklama_kaniti_sayilir(self):
        b = self.bulgular([
            olay("edit", file="src/pages/Home.jsx"),
            olay("test", cmd="npx playwright test", ok=True),
        ])
        self.assertNotIn(("BLOK", "tıklama kanıtı yok"), b)

    def test_view_alt_dizesi_yanlis_pozitif_uretmez(self):
        # 2026-08-01 yanlış pozitifi (4cast): "security-review/", "overview/",
        # "Interview/" içinde "view/" alt dizesi geçiyor — bunlar görünür
        # yüzey DEĞİL. Desen yol-parçası sınırına demirli olmalı.
        for yol in (".agents/skills/security-review/SKILL.md",
                    "docs/overview/rapor.md",
                    "src/Interview/notlar.md"):
            b = self.bulgular([olay("edit", file=yol)])
            self.assertEqual(b, set(), f"{yol} görünür yüzey sanıldı")

    def test_gercek_ui_dizini_hala_yakalanir(self):
        for yol in ("web/views/home.cshtml", "app/screens/Login.tsx",
                    "src/ui/button.css"):
            b = self.bulgular([olay("edit", file=yol),
                               olay("test", cmd="npx vitest run", ok=True)])
            self.assertIn(("BLOK", "tıklama kanıtı yok"), b,
                          f"{yol} görünür yüzey sayılmadı")

    def test_backend_degisikligi_tiklama_istemez(self):
        b = self.bulgular([
            olay("edit", file="src/services/hesap.py"),
            olay("test", cmd="unittest", ok=True),
        ])
        self.assertEqual(b, set())

    def test_zorunlu_skill_karsiliksizsa_uyarir(self):
        """SÜREÇ borcu uyarıdır, blok değil (politika değişikliği 2026-08-15).

        Gerekçe: bir blok +1 tam ajan turudur ve bağlamı yeniden okutur —
        kabaca 100 turluk router enjeksiyonu kadar pahalı. Ölçüm, kapının
        en sık ürettiği bulgunun bu olduğunu gösterdi (92 gate olayının
        çoğu). Yüklenmemiş bir süreç skill'i için o bedeli ödemek token'ı
        korumaya değil törene harcar. Borç GÖRÜNÜR kalır; yalnız turu
        kesmez. GÜVENLİK borcu bunun dışındadır — bir sonraki teste bak.
        """
        b = self.bulgular([olay("route", routed="implement-change")])
        self.assertIn(("UYARI", "zorunlu skill karşılıksız"), b)
        self.assertNotIn(("BLOK", "zorunlu skill karşılıksız"), b)

    def test_risk_yuzeyi_incelenmediyse_hala_bloklar(self):
        """Gevşetme SÜREÇ borcuyla sınırlıdır; güvenlik borcu BLOK kalır."""
        b = self.bulgular([
            olay("route", routed="security-review"),
            olay("edit", file="src/auth/login.py"),
            olay("test", cmd="python3 -m unittest", ok=True),
        ])
        self.assertIn(("BLOK", "risk yüzeyi incelenmedi"), b)

    def test_zorunlu_skill_yuklendiyse_temiz(self):
        b = self.bulgular([olay("route", routed="kernel-work"),
                           olay("skill", skill="kernel-work")])
        self.assertEqual(b, set())

    def test_gerekceli_atlama_bloklamaz(self):
        b = self.bulgular([
            olay("route", routed="implement-change"),
            olay("skipped", skill="implement-change", reason="misroute",
                 note="sohbet turu, kod değişmiyor"),
        ])
        self.assertEqual(b, set())

    def test_risk_yuzeyi_incelemesiz_bloklar(self):
        b = self.bulgular([
            olay("edit", file="src/auth/login.py"),
            olay("test", cmd="unittest", ok=True),
        ])
        self.assertIn(("BLOK", "risk yüzeyi incelenmedi"), b)

    def test_risk_yuzeyi_security_review_ile_gecer(self):
        b = self.bulgular([
            olay("skill", skill="security-review"),
            olay("edit", file="src/auth/login.py"),
            olay("test", cmd="unittest", ok=True),
        ])
        self.assertFalse([x for x in b if x[0] == "BLOK"])

    def test_buyuk_degisim_bagimsiz_inceleme_uyarir(self):
        olaylar = [olay("edit", file=f"src/m{i}.py") for i in range(6)]
        olaylar.append(olay("test", cmd="unittest", ok=True))
        b = self.bulgular(olaylar)
        self.assertIn(("UYARI", "bağımsız inceleme önerilir"), b)

    def test_onceki_tur_sayilmaz(self):
        # 'stop' öncesi olaylar geçmiş turdur; bu turun test kanıtını etkilemez
        b = self.bulgular([
            olay("edit", file="src/eski.py"),
            olay("stop"),
            olay("route", routed="research-with-evidence"),
            olay("skill", skill="research-with-evidence"),
        ])
        self.assertEqual(b, set())

    def test_ayni_imza_tekrar_bloklanmaz(self):
        olaylar = [olay("edit", file="src/app.py")]
        _b, sig = kapi.degerlendir(olaylar)
        self.assertFalse(kapi.zaten_bloklandi(olaylar, sig))
        olaylar.append(olay("gate", sig=sig))
        self.assertTrue(kapi.zaten_bloklandi(olaylar, sig))

    def test_uctan_uca_blok_json_uretir(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "e.jsonl")
            with open(log, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"kind": "edit", "file": "src/app.py"}) + "\n")
            p = subprocess.run(
                [sys.executable, os.path.join(ROOT, "bin", "kapi.py"),
                 "--log", log],
                input="{}", capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(p.returncode, 0)
            cikti = json.loads(p.stdout)
            self.assertEqual(cikti.get("decision"), "block")
            self.assertIn("test kanıtı yok", cikti["reason"])

    def test_bos_turda_sessiz(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "e.jsonl")
            p = subprocess.run(
                [sys.executable, os.path.join(ROOT, "bin", "kapi.py"),
                 "--log", log],
                input="{}", capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(p.returncode, 0)
            self.assertEqual(p.stdout.strip(), "")

    def test_stop_hook_active_kapan_kurmaz(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "e.jsonl")
            with open(log, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"kind": "edit", "file": "src/app.py"}) + "\n")
            p = subprocess.run(
                [sys.executable, os.path.join(ROOT, "bin", "kapi.py"),
                 "--log", log],
                input=json.dumps({"stop_hook_active": True}),
                capture_output=True, text=True, cwd=ROOT)
            self.assertNotIn('"decision": "block"', p.stdout)


if __name__ == "__main__":
    unittest.main()


class BlokTuruKapatmazTest(unittest.TestCase):
    """Bloklanan tur KAPANMIŞ sayılmaz — kanıt borcu susarak silinemez.

    Ölçülen açık (Codex incelemesi, 2026-08-12): blok kararından ÖNCE 'stop'
    yazılıyordu; ikinci deneme boş tur penceresi görüp SIFIR bulguyla temiz
    geçiyordu. 'Bir kez uyaran' kapı ile 'sessizce temizlenen' kapı arasında
    fark büyüktür: ilki zayıflık, ikincisi yanlış güvendir.
    """

    def kos(self, log, payload="{}"):
        p = subprocess.run(
            [sys.executable, os.path.join(ROOT, "bin", "kapi.py"),
             "--log", log],
            input=payload, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(p.returncode, 0)
        return p.stdout

    def olaylar(self, log):
        with open(log, encoding="utf-8") as fh:
            return [json.loads(s) for s in fh if s.strip()]

    def test_blok_stop_yazmaz_ikinci_deneme_sessiz_gecmez(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "e.jsonl")
            with open(log, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"kind": "edit", "file": "src/app.py"}) + "\n")

            # 1. deneme: BLOK — ve tur kapanmadı (stop YOK)
            self.assertIn('"decision": "block"', self.kos(log))
            self.assertNotIn("stop", [o.get("kind") for o in self.olaylar(log)],
                             "bloklanan tur 'stop' yazdı — borç silindi")

            # 2. deneme (kanıt hâlâ yok): kapan kurulmaz ama SESSİZ de geçilmez
            cikti = self.kos(log)
            self.assertNotIn('"decision": "block"', cikti)
            self.assertIn("⚠️", cikti, "ikinci deneme sessiz geçti — açık bu")
            # tur şimdi gerçekten kapandı
            self.assertIn("stop", [o.get("kind") for o in self.olaylar(log)])

            # 3. deneme: yeni tur, temiz pencere → sessiz
            self.assertEqual(self.kos(log).strip(), "")
