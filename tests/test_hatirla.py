#!/usr/bin/env python3
"""bin/hatirla.py — hafıza çağrısı aracının testleri."""
import importlib.util
import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "hatirla", os.path.join(ROOT, "bin", "hatirla.py"))
hatirla = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hatirla)


class EslesmeTest(unittest.TestCase):
    def test_turkce_kucuk_harf_ve_kelime_basi(self):
        self.assertTrue(hatirla.eslesiyor(["ratchet"], "Kalite RATCHET'i eklendi"))
        self.assertTrue(hatirla.eslesiyor(["kalite"], "kaliteyi ölçen kapı"))
        self.assertFalse(hatirla.eslesiyor(["ratchet"], "kalite kapısı"))

    def test_tum_kelimeler_gerekli(self):
        self.assertTrue(hatirla.eslesiyor(["kalite", "kapı"], "kalite kapısı"))
        self.assertFalse(hatirla.eslesiyor(["kalite", "ratchet"], "kalite kapısı"))


class KaynakTest(unittest.TestCase):
    def test_adr_kayitlari_tarihli_gelir(self):
        """ADR taraması çalışıyor mu — ADR'si olan her repoda.

        docs/decisions motor dizini DEĞİLDİR: bağlı projede hiç ADR
        olmayabilir. Test o zaman atlanır (görünür), 'ratchet' gibi
        kanoniğe özgü bir başlığı şart koşmaz.
        """
        adr = os.path.join(ROOT, "docs", "decisions")
        adlar = [a for a in os.listdir(adr)] if os.path.isdir(adr) else []
        if not adlar:
            self.skipTest("bu repoda ADR yok — tarama denenemez")
        kelimeler = [k for k in re.split(r"[^0-9A-Za-z]+", adlar[0])
                     if len(k) >= 5 and not k.isdigit()]
        if not kelimeler:
            self.skipTest("ADR adında aranabilir kelime yok")
        hits = hatirla.hatirla(kelimeler[0])
        self.assertTrue(hits, f"'{kelimeler[0]}' için kayıt bulunamadı")
        self.assertTrue(any("ADR" in satir for _t, satir in hits))

    def test_git_kayitlari_tarihli_gelir(self):
        """Git taraması çalışıyor mu — HANGİ repoda olursa olsun.

        İlk yazımda sorgu 'grilling' idi: kanonik repoda geçen bir commit
        konusu. Bu test her projeye taşınır (tests/ motor dizinidir) ve
        bağlı projede o commit yoktur — 4cast kurulumunda kırmızı verdi
        (2026-08-12). Taşınan test, kanonik repo GEÇMİŞİNİ şart koşamaz;
        sorgu artık reponun kendi son commit'inden türetiliyor.
        """
        p = subprocess.run(["git", "log", "-1", "--pretty=%s"],
                           capture_output=True, text=True, cwd=ROOT)
        if p.returncode != 0 or not p.stdout.strip():
            self.skipTest("git geçmişi yok — tarama denenemez")
        kelimeler = [k for k in re.split(r"[^0-9A-Za-zçğıöşüÇĞİÖŞÜ]+", p.stdout)
                     if len(k) >= 5]
        if not kelimeler:
            self.skipTest("son commit konusunda aranabilir kelime yok")
        hits = hatirla.hatirla(kelimeler[0])
        self.assertTrue(any(satir.startswith("commit") for _t, satir in hits),
                        f"'{kelimeler[0]}' için commit kaydı yok: {hits}")
        # her kayıt tarihli — 'tarihiyle hatırlat' sözleşmesi
        for tarih, _s in hits:
            self.assertRegex(tarih, r"^(\d{4}-\d{2}-\d{2}|\?{4}-\?{2}-\?{2})$")

    def test_bos_sonuc_yokluk_kaniti_degildir(self):
        hits = hatirla.hatirla("boyle-bir-konu-hic-olmadi-xyzq")
        self.assertEqual(hits, [])
