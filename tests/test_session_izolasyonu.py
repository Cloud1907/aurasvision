#!/usr/bin/env python3
"""Session izolasyonu — eşzamanlı oturumlar birbirinin kanıtını sahiplenemez.

Neden ayrı bekçi: olay kaydı TEK dosyadır ve `.claude/worktrees/` altında
aynı anda birden çok oturum çalışabilir (bu repoda 5 worktree ölçüldü,
2026-08-15). Kapı "bu turun olayları"nı son GLOBAL `stop`tan çıkarıyordu;
yani B oturumunun testi A oturumunun düzenlemesine kanıt sayılabiliyordu —
kapı, olmadığı bir şeyi gördüğünü sanır.

İkinci kusur aynı kökten: `route.py` olay kaydına session yazmıyordu (286
route olayının 0'ı taşıyordu, ölçüm 2026-08-15). Alan `run_event.ALLOWED`
listesinde vardı, YAZAN yoktu — şema hazır, sözleşme boştu.

Kural tek cümle: bir turun kanıtı yalnız o turun oturumundan gelebilir.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortam import pyyaml_gerekir  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "bin", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kapi = _load("kapi")
route = _load("route")
run_event = _load("run_event")


def olay(kind, session=None, **kw):
    d = {"kind": kind}
    if session is not None:
        d["session"] = session
    d.update(kw)
    return d


class SessionIzolasyonuTest(unittest.TestCase):
    def test_bu_turun_olaylari_session_suzer(self):
        """Başka oturumun olayı bu turun penceresine girmez."""
        olaylar = [
            olay("edit", "AAA", file="src/a.py"),
            olay("edit", "BBB", file="src/b.py"),
            olay("test", "BBB", cmd="pytest", ok=True),
        ]
        tur = kapi.bu_turun_olaylari(olaylar, session="AAA")
        self.assertEqual([o.get("file") for o in tur if o.get("file")],
                         ["src/a.py"])

    def test_baska_oturumun_testi_kanit_sayilmaz(self):
        """A düzenledi, B test koşturdu → A'nın turu BLOKLANIR."""
        olaylar = [
            olay("edit", "AAA", file="src/a.py"),
            olay("test", "BBB", cmd="python3 -m unittest", ok=True),
        ]
        bulgular, _sig = kapi.degerlendir(olaylar, session="AAA")
        self.assertIn(("BLOK", "test kanıtı yok"),
                      {(t, b) for t, b, _a in bulgular})

    def test_kendi_oturumunun_testi_kanit_sayilir(self):
        """Aynı oturumun testi kanıttır — süzme fazla katı olmamalı."""
        olaylar = [
            olay("edit", "AAA", file="src/a.py"),
            olay("test", "AAA", cmd="python3 -m unittest", ok=True),
        ]
        bulgular, _sig = kapi.degerlendir(olaylar, session="AAA")
        self.assertNotIn("test kanıtı yok", {b for _t, b, _a in bulgular})

    def test_session_yoksa_eski_davranis_korunur(self):
        """Session bilinmiyorsa süzme yapılmaz (geriye uyum).

        Kayıtta session taşımayan eski satırlar var; onları yok saymak
        geçmiş kanıtı silmek olurdu.
        """
        olaylar = [olay("edit", None, file="src/a.py"),
                   olay("test", None, cmd="pytest", ok=True)]
        bulgular, _sig = kapi.degerlendir(olaylar, session=None)
        self.assertNotIn("test kanıtı yok", {b for _t, b, _a in bulgular})

    def test_imza_bulgu_turlerini_de_kapsar(self):
        """Aynı dosya kümesi farklı borçla ikinci kez bloklanabilmeli.

        2026-08-15 ölçümü: imza YALNIZ düzenlenen dosyalardan üretiliyordu;
        düzenlemesiz turda "".join([]) sabit e3b0c44298fc veriyordu ve 92
        gate olayının 39'u bu imzayı taşıyordu — ilki dışındaki 38 tur
        "zaten bloklandı" sayılıp muaf kaldı.
        """
        _b1, imza_test = kapi.degerlendir([olay("edit", "A", file="src/a.py")],
                                          session="A")
        _b2, imza_skill = kapi.degerlendir(
            [olay("route", "A", routed="implement-change")], session="A")
        self.assertNotEqual(
            imza_test, imza_skill,
            "farklı borçlar aynı imzayı üretiyor — biri diğerini muaf kılar")

    def test_iki_dusunmesiz_tur_ayri_ayri_bloklanir(self):
        """Düzenlemesiz iki farklı skill borcu aynı imzaya düşmemeli."""
        _b1, i1 = kapi.degerlendir([olay("route", "A", routed="kernel-work")],
                                   session="A")
        _b2, i2 = kapi.degerlendir(
            [olay("route", "A", routed="security-review")], session="A")
        self.assertNotEqual(i1, i2)

    @pyyaml_gerekir
    def test_route_olayi_session_tasir(self):
        """Router kararı hangi oturumda alındığı bilinmeden kaydedilemez."""
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "events.jsonl")
            cfg = route.load_rules()
            route._kaydet("cache ekle", cfg, ROOT, session="DEADBEEF",
                          log=log)
            kayitlar = [json.loads(s) for s in open(log, encoding="utf-8")
                        if s.strip()]
            self.assertTrue(kayitlar, "route olayı hiç yazılmadı")
            self.assertEqual(kayitlar[0].get("session"), "DEADBEEF")

    def test_durum_tablosu_oturumlari_karistirmaz(self):
        """İki oturumun turu birbirini kapatmaz, skill'i birbirine düşmez.

        Eski hâlde tur sınırı GLOBAL çiziliyordu: B'nin route olayı A'nın
        turunu kapatıyor, A'nın yüklediği skill B'nin turuna düşüyor ve tablo
        gerçekte olmayan bir SAPMA gösteriyordu.
        """
        durum = _load("durum")
        turlar = durum.turlari_cikar([
            {"kind": "route", "session": "AAA", "routed": "implement-change"},
            {"kind": "route", "session": "BBB", "routed": "research-with-evidence"},
            {"kind": "skill", "session": "AAA", "skill": "implement-change"},
            {"kind": "skill", "session": "BBB", "skill": "research-with-evidence"},
        ])
        self.assertEqual([t["durum"] for t in turlar], ["uyumlu", "uyumlu"])

    def test_append_eszamanli_yazimda_satir_kaybetmez(self):
        """Kilitsiz append satırları iç içe geçirebilir; kilit bunu keser."""
        import threading
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "events.jsonl")
            uzun = "x" * 4000            # tek write() sınırını aşan gövde

            def yaz(i):
                for _ in range(20):
                    run_event.append({"kind": "bash", "cmd": f"{i}{uzun}"}, log)

            is_parcaciklari = [threading.Thread(target=yaz, args=(i,))
                               for i in range(4)]
            for t in is_parcaciklari:
                t.start()
            for t in is_parcaciklari:
                t.join()
            satirlar = [s for s in open(log, encoding="utf-8") if s.strip()]
            self.assertEqual(len(satirlar), 80)
            for s in satirlar:
                json.loads(s)            # bozuk satır = iç içe geçmiş yazım


if __name__ == "__main__":
    unittest.main()
