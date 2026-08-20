#!/usr/bin/env python3
"""Karşılamanın 📌 Geçmiş satırı KAYITTAN gelsin, modelin belleğinden değil.

2026-08-15 kullanıcı bulgusu: "beni konuşma olarak karşılayan biri olacak ve
sanki hafızayı söyleyecekti" — olmuyordu. Kusur `hatirla.py`'de değildi;
araç vardı, ÇAĞIRAN yoktu. Karşılama metni ajana "`bin/hatirla.py <konu>` ile
bak" diyordu; bakmak ajanın takdirindeydi ve ajan her turda atlıyordu.
Yazılmış ama çağrılmayan araç = kural belgede var, sistemde yok.

Bu testler bağlantıyı kilitler: router hatırlamayı KENDİSİ koşar ve tarihli
kaydı prompt'a enjekte eder. Ajanın yapacağı iş kalan tek şeydir — okumak.
"""
import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortam import pyyaml_gerekir  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
import hatirla as ht  # noqa: E402
import davranis  # noqa: E402


def _yukle(ad):
    spec = importlib.util.spec_from_file_location(
        ad, os.path.join(ROOT, "bin", f"{ad}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


route = _yukle("route")
TARIH = ht.TARIH


class AnahtarTest(unittest.TestCase):
    """Cümle sorgusu hiçbir şey bulmaz — önce anahtar çıkarılmalı."""

    def test_tetik_varsa_tetik_kullanilir(self):
        # Router zaten "bu istek neyle ilgili" hesabını yaptı; tekrar tahmin
        # etmek o hesabı çöpe atmaktır.
        self.assertEqual(ht.anahtarlar("upuzun bir cümle burada", ["hafıza"]),
                         ["hafıza"])

    def test_tetik_yoksa_uzun_kelimelere_duser(self):
        anahtar = ht.anahtarlar("bağlı repolar kuralları kullanıyor mu", [])
        self.assertTrue(anahtar, "tetiksiz turda hafıza tamamen susuyor")
        self.assertNotIn("mu", anahtar, "kısa/durak kelime sorguya girdi")

    def test_bos_girdi_bos_doner(self):
        self.assertEqual(ht.anahtarlar("  ", []), [])


class CokluHatirlamaTest(unittest.TestCase):
    """hatirla() TÜM kelimeleri ister; karşılama VEYA'ya ihtiyaç duyar."""

    def test_tek_kelimede_bulunan_coklu_sorguda_da_bulunur(self):
        tek = ht.hatirla("kalite", 3)
        if not tek:
            self.skipTest("bu repoda 'kalite' kaydı yok")
        coklu = ht.hatirla_coklu(["kalite", "zzzyoktur"], 3)
        self.assertTrue(coklu, "VEYA sorgusu tek kelimede bulunanı kaybetti")

    def test_ayni_kayit_tekrarlanmaz(self):
        coklu = ht.hatirla_coklu(["kalite", "kalite"], 5)
        satirlar = [s for _t, s in coklu]
        self.assertEqual(len(satirlar), len(set(satirlar)))

    def test_kayit_yoksa_bos_doner(self):
        self.assertEqual(ht.hatirla_coklu(["zzzyokboylebirkelime"], 3), [])


@pyyaml_gerekir
class KarsilamaEnjeksiyonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = route.load_rules()

    def ciktı(self, prompt):
        return route.render(prompt, self.cfg, pdir=ROOT)[0]

    def test_gecmis_kayittan_enjekte_edilir(self):
        """Asıl sözleşme: tarihli kayıt prompt'un İÇİNDE gelir.

        Kayıt KENDİ fixture'ımızdan verilir, ortamdan DEĞİL. Ölçüm 2026-08-16:
        test kanonik repo'nun git geçmişine dayanıyordu ve `tests/` her bağlı
        projeye taşındığı için TAZE KURULUM KIRMIZI BAŞLIYORDU — yeni repoda
        eşleşecek commit yok, olması da beklenmez. Bu tam olarak kernel'in
        kendi yasakladığı hâl: "kutudan kırmızı çıkan kurulum, insana kapıyı
        baştan yok saymayı öğretir" (4Flow, 2026-08-07).

        Ortam verisiyle test edilen şey mekanizma değil, o repo'nun tarihidir.
        Boş kayıt hâli zaten ayrı testte (`test_kayit_yoksa_uydurulmaz`).
        """
        enjekte = getattr(route, "enjekte", None)
        if enjekte is None:                      # router degrade modda
            self.skipTest("enjekte modülü yüklenmemiş")
        gercek = enjekte.hatirla.karsilama_kayitlari
        enjekte.hatirla.karsilama_kayitlari = lambda *a, **k: [
            ("2026-08-15", "commit abc1234  Kalite ratchet tabanı yükseltildi")]
        self.addCleanup(setattr, enjekte.hatirla, "karsilama_kayitlari", gercek)
        metin = self.ciktı("kalite ratchet tabanını yükseltelim mi")
        self.assertIn("📌 Geçmiş", metin)
        self.assertRegex(metin, TARIH.pattern,
                         "karşılamada tarihli tek bir kayıt bile yok")

    def test_kayit_yoksa_uydurulmaz(self):
        # Ölçüt: kayıt yokken ajana (a) ne yazacağı söylenir, (b) uydurma
        # yasağı hatırlatılır. Cümlenin kendisi değil bu iki işaret aranır.
        metin = self.ciktı("zzzyokboylebirkelime zzzbaskasiyok")
        self.assertIn("kayıt yok", metin)
        self.assertIn("uydurma", metin)

    def test_ajana_artik_hatirla_kos_denmez(self):
        # Mekanizma devraldı; talimat kalırsa ajan iki kaynak arasında seçim
        # yapar ve kendi belleğini "kayıt" diye yazabilir.
        self.assertNotIn("bin/hatirla.py", davranis.KARSILAMA)

    def test_atlama_gerekcesi_esnek_degil(self):
        # Eski metin "küçük/NET işte atla" diyordu; "net" elastik bir ölçüdür
        # ve büyük ama açık işler de bu boşluktan atlandı (2026-08-15). Mikro
        # iş muafiyeti korunur (skill eval #2), ölçü boyuta bağlanır.
        #
        # Ölçüt İFADEYE değil ANLAMA demirlenir (2026-08-15): eski hâli
        # "takip turu DEĞİLDİR" dizesini birebir arıyordu ve metni
        # kısaltmak — davranış aynı kalsa bile — testi kırıyordu. Dizge
        # eşleşmesi sözleşmeyi değil yazımı korur.
        metin = davranis.KARSILAMA.lower()
        self.assertNotIn("net işte", metin)
        self.assertIn("mikro iş", metin)          # muafiyet boyuta bağlı
        self.assertIn("takip turu", metin)        # takip turu muafiyeti var
        self.assertIn("değildir", metin)          # ve sınırı yazılı

    def test_acik_komut_turunda_karsilama_da_hafiza_da_yok(self):
        metin = self.ciktı("/kernel-work router'ı düzelt")
        self.assertNotIn("📌 Geçmiş", metin)

    def test_hafiza_cokerse_router_susar(self):
        # Router asla bloklamaz (kernel-work sözleşmesi): hatırlama bir
        # kolaylıktır, kapı değil.
        eski = ht.hatirla_coklu
        ht.hatirla_coklu = lambda *a, **k: 1 / 0
        try:
            metin = self.ciktı("kalite ratchet tabanı")
        finally:
            ht.hatirla_coklu = eski
        self.assertIn("[AurasAgents router]", metin)


if __name__ == "__main__":
    unittest.main()
