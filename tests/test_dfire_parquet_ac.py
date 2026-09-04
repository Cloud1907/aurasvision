"""D-Fire parquet açıcı — gerçek veri seti İSTEMEZ, parquet bellekte üretilir.

Neden gerekli: aynanın ham `train/images` ağacı eksik çıktı (2026-09-02: 7.222
görüntü / 21.527 olması gerekirken), tam veri yalnız parquet'te. Bu açıcı o
yüzden hattın parçası oldu ve iki sessiz hata riski taşıyor:

  · Şema kayması — sütun adı değişirse boş bir veri seti üretip eğitimi
    sessizce anlamsızlaştırır; bu yüzden eksik sütun AÇIK hata verir.
  · Negatif kare kaybı — `label` boş dizeyse bu geçerli bir NEGATİF karedir,
    atlanacak bir satır değil.
"""
import tempfile
import unittest
from pathlib import Path

from scripts.dfire_parquet_ac import (ParquetHatasi, etiket_metni,
                                      goruntu_baytlari, parcalari_bul,
                                      split_yaz, sutunlari_dogrula)


def _jpeg() -> bytes:
    import io

    from PIL import Image
    tampon = io.BytesIO()
    Image.new("RGB", (32, 24), (5, 5, 5)).save(tampon, format="JPEG")
    return tampon.getvalue()


def _parquet_yaz(yol: Path, satirlar: list[dict]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    pq.write_table(pa.Table.from_pylist(satirlar), yol)


class SutunDogrulama(unittest.TestCase):
    def test_tam_sema_gecer(self):
        sutunlari_dogrula(["image", "label", "filename"])

    def test_eksik_sutun_acik_hata(self):
        """Sessizce boş veri seti üretmektense patlamalı."""
        with self.assertRaises(ParquetHatasi) as c:
            sutunlari_dogrula(["image", "filename"])
        self.assertIn("label", str(c.exception))


class GoruntuBaytlari(unittest.TestCase):
    def test_bytes_alanindan_okur(self):
        self.assertEqual(goruntu_baytlari({"bytes": b"abc", "path": None}), b"abc")

    def test_ham_bytes_kabul(self):
        self.assertEqual(goruntu_baytlari(b"xy"), b"xy")

    def test_okunamayan_satir_hata(self):
        with self.assertRaises(ParquetHatasi):
            goruntu_baytlari({"bytes": None, "path": None})


class EtiketMetni(unittest.TestCase):
    def test_bos_negatif_karedir(self):
        self.assertEqual(etiket_metni(""), "")
        self.assertEqual(etiket_metni(None), "")

    def test_kutu_metni_korunur(self):
        self.assertEqual(etiket_metni(" 0 0.5 0.5 0.2 0.2 "), "0 0.5 0.5 0.2 0.2")


class SplitYaz(unittest.TestCase):
    def _kur(self, d: Path) -> dict:
        veri = d / "data"
        veri.mkdir(parents=True)
        _parquet_yaz(veri / "train-00000-of-00001.parquet", [
            {"image": {"bytes": _jpeg(), "path": "a.jpg"}, "label": "",
             "filename": "a.jpg"},
            {"image": {"bytes": _jpeg(), "path": "b.jpg"},
             "label": "0 0.5 0.5 0.2 0.2\n1 0.4 0.4 0.1 0.1", "filename": "b.jpg"},
        ])
        return {"veri": veri}

    def test_negatif_kare_bos_etiketle_yazilir(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._kur(d)
            s = split_yaz(parcalari_bul(d / "data", "train"), d / "out")
            self.assertEqual(s["goruntu"], 2)
            self.assertEqual(s["negatif"], 1)
            self.assertEqual(s["kutu"], 2)
            self.assertTrue((d / "out" / "images" / "a.jpg").is_file())
            # negatif kare etiketi VAR ama boş — dosya hiç yazılmazsa da
            # dönüştürücü negatif sayar, ama izlenebilirlik için yazılır
            self.assertEqual((d / "out" / "labels" / "a.txt").read_text(), "")

    def test_pozitif_etiket_satirlari_korunur(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._kur(d)
            split_yaz(parcalari_bul(d / "data", "train"), d / "out")
            metin = (d / "out" / "labels" / "b.txt").read_text(encoding="utf-8")
            self.assertEqual(metin.strip().splitlines(),
                             ["0 0.5 0.5 0.2 0.2", "1 0.4 0.4 0.1 0.1"])

    def test_goruntu_gercekten_acilabilir(self):
        """Yazılan bayt gerçek bir görüntü olmalı — boyut okuması buna bağlı."""
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._kur(d)
            split_yaz(parcalari_bul(d / "data", "train"), d / "out")
            with Image.open(d / "out" / "images" / "a.jpg") as im:
                self.assertEqual((im.width, im.height), (32, 24))


class ParcaBulma(unittest.TestCase):
    def test_split_adina_gore_secer(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            for ad in ("train-00000-of-00002.parquet", "train-00001-of-00002.parquet",
                       "test-00000-of-00001.parquet"):
                (d / ad).write_bytes(b"")
            self.assertEqual(len(parcalari_bul(d, "train")), 2)
            self.assertEqual(len(parcalari_bul(d, "test")), 1)

    def test_bulunamazsa_bos_liste(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(parcalari_bul(Path(t), "train"), [])


if __name__ == "__main__":
    unittest.main()
