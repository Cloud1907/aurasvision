"""tespit_karolu — kare bölme, kutu geri taşıma ve bindirme birleştirme (model gerekmez)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _numpy():
    try:
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_numpy(), "numpy gerekir")
class KaroTest(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from src import fire
        self.fire = fire
        self.np = np

    def _sahte_dedektor(self, parlak_esik=100):
        """Parçadaki parlak piksellerin sınır kutusunu 'fire' olarak döner."""
        np = self.np

        class D:
            def tespit(self, parca):
                ys, xs = np.where(parca[:, :, 2] > parlak_esik)
                if len(xs) == 0:
                    return []
                return [("fire", float(xs.min()), float(ys.min()),
                         float(xs.max() + 1), float(ys.max() + 1), 0.9)]
        return D()

    def test_karo_yok_dogrudan(self):
        img = self.np.zeros((100, 200, 3), dtype=self.np.uint8)
        img[10:20, 30:40, 2] = 255
        t = self.fire.tespit_karolu(self._sahte_dedektor(), img, 1)
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0][1:5], (30.0, 10.0, 40.0, 20.0))

    def test_kutu_geri_tasinir(self):
        """Sağ-alt karodaki nesne tam kare koordinatına dönmeli."""
        img = self.np.zeros((200, 400, 3), dtype=self.np.uint8)
        img[150:160, 300:320, 2] = 255
        t = self.fire.tespit_karolu(self._sahte_dedektor(), img, 2)
        self.assertEqual(len(t), 1, t)
        self.assertEqual(t[0][1:5], (300.0, 150.0, 320.0, 160.0))

    def test_bindirmede_cift_kutu_birlesir(self):
        """Karo sınırındaki nesne iki karoda da çıkar; tek kutuya inmeli."""
        img = self.np.zeros((200, 400, 3), dtype=self.np.uint8)
        img[95:105, 195:205, 2] = 255       # tam ortada, dört karonun bindirmesinde
        t = self.fire.tespit_karolu(self._sahte_dedektor(), img, 2, bindirme=0.1)
        self.assertEqual(len(t), 1, t)
        self.assertEqual(t[0][1:5], (195.0, 95.0, 205.0, 105.0))

    def test_bos_kare(self):
        img = self.np.zeros((200, 400, 3), dtype=self.np.uint8)
        self.assertEqual(self.fire.tespit_karolu(self._sahte_dedektor(), img, 2), [])


if __name__ == "__main__":
    unittest.main()
