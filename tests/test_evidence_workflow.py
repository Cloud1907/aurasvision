#!/usr/bin/env python3
"""Kanıt workflow'unun tetikleyici sözleşmesi.

2026-08-06 GitHub Actions kesintisi (githubstatus "Incident with Actions",
15:22:49Z): webhook teslimatı bozulunca push/pull_request hiç run üretmedi,
yalnız workflow_dispatch çalıştı. Kanıt üretiminin TEK yolu otomatik olay
olamaz — aksi hâlde kesinti boyunca hiçbir PR bağımsız makine kanıtı
üretemez ve merge kararı yerel çıktıya kalır.
"""
import os
import re
import sys
import tempfile
import unittest

# Keşif `tests/`i sys.path'e koyar, `python3 -m unittest tests.test_x` koymaz.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortam import pyyaml_gerekir, yaml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _kd():
    """Motor listesi modülü — yol çözücüsü için."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_kd", os.path.join(ROOT, "bin", "kernel_dosyalari.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
WF = os.path.join(ROOT, ".github", "workflows", "evidence.yml")
VALIDATE = os.path.join(ROOT, "bin", "validate.py")


def oku(yol):
    with open(yol, encoding="utf-8") as fh:
        return fh.read()


def tetikleyiciler():
    d = yaml.safe_load(oku(WF))
    # PyYAML 'on:' anahtarını boolean True'ya çevirir (YAML 1.1 mirası).
    return d.get(True, d.get("on", {})) or {}


class EvidenceWorkflowTest(unittest.TestCase):
    # Yalnız yaml AYRIŞTIRAN testler atlanır; kalanlar metin üstünde çalışır
    # ve PyYAML'sız yorumlayıcıda da koşmaya devam eder.
    @pyyaml_gerekir
    def test_uc_tetikleyici_de_tanimli(self):
        on = tetikleyiciler()
        for t in ("pull_request", "push", "workflow_dispatch"):
            self.assertIn(t, on, f"evidence.yml '{t}' tetikleyicisini kaybetmiş")

    def test_elle_tetikleme_bekcisi_gercekten_calisir(self):
        """Bekçi silinirse tetikleyici sessizce kaybolur — bu test onu kilitler.

        Ölçü DİZGE DEĞİL DAVRANIŞ (2026-08-16): eski hâli `validate.py`nin
        metninde "workflow_dispatch" arıyordu ve bekçi `bin/dogrula_ci.py`ye
        taşınınca — davranış aynı kalmasına rağmen — kırıldı. Dizge araması
        bekçinin YERİNİ kilitler, VARLIĞINI değil. Artık bekçi, tetikleyicisi
        sökülmüş bir workflow üstünde koşturulup gerçekten şikâyet ediyor mu
        diye sınanır.
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_dci", os.path.join(ROOT, "bin", "dogrula_ci.py"))
        dci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dci)

        hatalar = []
        dci.kur(lambda kosul, mesaj: None if kosul else hatalar.append(mesaj))
        with tempfile.TemporaryDirectory() as td:
            hedef = os.path.join(td, ".github", "workflows")
            os.makedirs(hedef)
            bozuk = oku(WF).replace("  workflow_dispatch:\n", "")
            with open(os.path.join(hedef, "evidence.yml"), "w",
                      encoding="utf-8") as fh:
                fh.write(bozuk)
            eski_root = dci.ROOT
            dci.ROOT = td
            try:
                dci.test_workflow()
            finally:
                dci.ROOT = eski_root
        self.assertTrue(
            any("workflow_dispatch" in h for h in hatalar),
            "tetikleyici sökülmüş workflow bekçiden GEÇTİ — bekçi kör")

    @pyyaml_gerekir
    def test_workflow_yaml_gecerli(self):
        d = yaml.safe_load(oku(WF))
        self.assertIn("jobs", d, "evidence.yml 'jobs' taşımıyor")

    def test_kanit_uretimi_ve_artifact_adimi_duruyor(self):
        metin = oku(WF)
        for parca in ("make_evidence.py", "upload-artifact", "validate.py"):
            self.assertIn(parca, metin, f"evidence.yml '{parca}' kaybetmiş")


class PyyamlKurulumuTest(unittest.TestCase):
    """Kanıt workflow'u kurulamadığı makinede kanıt üretemez.

    Ölçüm 2026-08-16 (OICommand, kanıt köprüsü): Homebrew/sistem python3'ü
    çıplak `pip install`i PEP 668 ile REDDEDER (externally-managed-environment).
    GitHub'ın kendi imajında bu sorun yoktu; self-hosted runner'a geçilince
    kernel job'ı İLK adımda düştü ve hiçbir check koşamadı.

    İki şey birden korunmalı ve biri diğerinin yerine geçmez:
      - geri düşüş olmalı (yoksa köprüde kanıt üretilemez),
      - sürüm sabiti HER yolda kalmalı (yoksa "aynı doğrulama bağımsız
        makinede tekrarlanır" iddiası bozulur — her koşu başka sürüm çeker).
    """

    def setUp(self):
        self.adim = next(
            (a for a in yaml.safe_load(oku(WF))["jobs"]["kernel"]["steps"]
             if "PyYAML" in (a.get("name") or "")), None)
        self.assertIsNotNone(self.adim, "PyYAML kurulum adımı kaybolmuş")
        self.komut = self.adim.get("run", "")

    def test_pep668_geri_dususu_var(self):
        self.assertTrue(
            "--break-system-packages" in self.komut or "--user" in self.komut,
            "PEP 668 geri düşüşü yok — self-hosted runner'da kernel job'ı "
            "ilk adımda düşer ve hiçbir kanıt üretilemez")

    def test_surum_sabiti_her_yolda_korunur(self):
        yollar = [s for s in self.komut.split("||") if "pip install" in s]
        self.assertGreaterEqual(len(yollar), 2, "geri düşüş yolu yok")
        for y in yollar:
            self.assertRegex(
                y, r"pyyaml==\d+\.\d+",
                "geri düşüş yolu sürüm sabitini düşürmüş — kurulum yolu "
                "değişebilir, KURULAN SÜRÜM değişemez")


if __name__ == "__main__":
    unittest.main()


class WorkflowEnjeksiyonTest(unittest.TestCase):
    """Güvenilmeyen girdi `run:` bloğuna DOĞRUDAN yazılamaz.

    2026-08-07'de gerçekleşti: `TITLE="${{ github.event.pull_request.title }}"`
    satırında PR başlığı tırnak içeriyordu, dizeyi kapattı ve kalanı komut
    olarak çalıştı (exit 127). Kazaydı — ama PR başlığı yazabilen herkesin
    CI runner'ında komut çalıştırabileceği anlamına geliyordu.

    Doğrusu `env:` ile geçirmek: kabuk değeri VERİ olarak görür, KOD olarak
    değil. GitHub'ın kendi güvenli-kullanım dokümanı da bunu söylüyor.
    """

    WF_DIR = os.path.join(ROOT, ".github", "workflows")
    # PR/issue/branch metni — saldırganın yazabildiği alanlar.
    GUVENILMEYEN = re.compile(
        r"\$\{\{\s*github\.(event\.(pull_request|issue|comment)\.|head_ref)")

    def workflow_dosyalari(self):
        if not os.path.isdir(self.WF_DIR):
            return []
        return [os.path.join(self.WF_DIR, f)
                for f in sorted(os.listdir(self.WF_DIR))
                if f.endswith((".yml", ".yaml"))]

    def test_run_blogunda_guvenilmeyen_interpolasyon_yok(self):
        for yol in self.workflow_dosyalari():
            with open(yol, encoding="utf-8") as fh:
                satirlar = fh.readlines()
            icinde_run, girinti = False, 0
            for no, satir in enumerate(satirlar, 1):
                sivri = len(satir) - len(satir.lstrip())
                if re.match(r"\s*run:\s*\|?\s*$", satir) or \
                        re.match(r"\s*run:\s+\S", satir):
                    icinde_run, girinti = True, sivri
                    continue
                if icinde_run and satir.strip() and sivri <= girinti:
                    icinde_run = False
                if icinde_run and self.GUVENILMEYEN.search(satir):
                    self.fail(
                        f"{os.path.basename(yol)}:{no} — güvenilmeyen girdi "
                        f"run: bloğuna doğrudan yazılmış (komut enjeksiyonu). "
                        f"env: ile geçir.\n    {satir.strip()}")


class KapsamSiniriTest(unittest.TestCase):
    """Sistem neyi zorlamadığını açıkça söylemeli (2026-08-07).

    Kapsam sınırını gizleyen sistem, kapsamı dar olandan tehlikelidir:
    kullanıcı korunduğunu sanır. Ölçüm: 10 aşamanın 4'ünde hiç kapı yok.
    """

    BELGE = (_kd().yol_coz(ROOT, "docs/yasam-dongusu-kapsami.md")
             or os.path.join(ROOT, "docs", "yasam-dongusu-kapsami.md"))
    AGENTS = os.path.join(ROOT, "AGENTS.md")

    def test_kapsam_belgesi_var(self):
        self.assertTrue(os.path.isfile(self.BELGE),
                        "yaşam döngüsü kapsam haritası kaybolmuş")

    def test_agents_md_referans_veriyor(self):
        # Referans yoksa belge yetim kalır ve okunmaz
        self.assertIn("yasam-dongusu-kapsami", oku(self.AGENTS))

    def test_belge_kapsanmayan_asamalari_adiyla_sayiyor(self):
        # Genel "bazı eksikler var" cümlesi yeterli değil; hangi aşama?
        metin = oku(self.BELGE).lower()
        for asama in ("keşif", "tasarım", "operasyon", "ölçme"):
            self.assertIn(asama, metin, f"'{asama}' aşaması belgede yok")

    def test_belge_olculemez_alani_ayirt_ediyor(self):
        # Ölçülemeyeni kapıya bağlamaya çalışmak sahte kesinlik üretir
        metin = oku(self.BELGE).lower()
        self.assertIn("ölçülemez", metin)
        self.assertIn("sahte kesinlik", metin)
