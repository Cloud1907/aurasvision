#!/usr/bin/env python3
"""Hüküm sözleşmesi — ayrıştırma ve tutarlılık (bin/hukum.py).

Bu dosyadaki her test, kapının bir kez SIZDIRDIĞI bir kaçağı kilitler.
Hepsi düzeltmeden önce kırmızıydı. Ders her turda aynıydı: hüküm
ayrıştırmasında serbest bırakılan her uç bir kaçak üretti — bu yüzden
sözleşme artık KARA LİSTE değil BEYAZ LİSTE (bkz. bin/codex-review.sh).
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
_spec = importlib.util.spec_from_file_location(
    "hukum", os.path.join(ROOT, "bin", "hukum.py"))
incele = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(incele)

TEMIZ = {"P0": [], "P1": [], "P2": []}


class AyiklamaTest(unittest.TestCase):
    def test_bulgular_ve_sonuc_okunur(self):
        metin = ("[P0] api.py:12 — yetki kontrolü yok — başka kullanıcının "
                 "kaydı okunur\n[P2] stil notu\nSONUC: 2 bulgu (en yuksek: P0)")
        b, s, ok = incele.bulgulari_ayikla(metin)
        self.assertTrue(ok)
        self.assertEqual(len(b["P0"]), 1)
        self.assertEqual(len(b["P2"]), 1)
        self.assertIn("2 bulgu", s)

    def test_temiz_cikti(self):
        b, s, ok = incele.bulgulari_ayikla("Inceleme tamam.\nSONUC: TEMIZ")
        self.assertTrue(ok)
        self.assertEqual(b, TEMIZ)
        self.assertEqual(s.upper(), "TEMIZ")

    def test_sonuc_satiri_yoksa_okunamadi(self):
        # En tehlikeli hâl: çıktı bozuk ama "bulgu yok" diye geçmek
        _b, _s, ok = incele.bulgulari_ayikla("codex hata verdi, bağlantı yok")
        self.assertFalse(ok)

    def test_bos_cikti_okunamadi(self):
        self.assertFalse(incele.bulgulari_ayikla("")[2])

    def test_birden_cok_sonuc_satiri_okunamadi_sayilir(self):
        """İki hüküm varsa hangisinin geçerli olduğu belirsizdir.

        Codex bulgusu (PR #38, altıncı tur). `search` İLK eşleşmeyi alıyordu,
        yani sonraki olumsuz hüküm sessizce yok sayılıyordu:

            [P2] ufak not
            SONUC: 1 bulgu (en yuksek: P2)
            SONUC: TEMIZ DEGIL

        Birinci satır tutarlı görünür, P2 merge'i durdurmaz ve auto riskli PR
        birleşirdi. İstem tek satırlık hüküm istiyor; ikisi varsa çıktı
        sözleşmeye uymamıştır — "okunamadı"dır.
        """
        metin = ("[P2] ufak not\nSONUC: 1 bulgu (en yuksek: P2)\n"
                 "SONUC: TEMIZ DEGIL")
        _b, _s, ok = incele.bulgulari_ayikla(metin)
        self.assertFalse(ok, "iki hüküm varsa çıktı okunmuş sayılamaz")


class HukumSatirBasindaTest(unittest.TestCase):
    """Hüküm KENDİ SATIRINDA olmalı — düz metin içindeki anış hüküm değildir.

    Codex bulgusu (PR #38 — P0). `SONUC` deseni satır başına sabitli değildi,
    yani inceleyicinin "beklenen biçim şöyleydi: SONUC: TEMIZ" gibi bir
    AÇIKLAMASI geçerli hüküm sayılıyordu. İnceleme tamamlanamamışken bile
    "temiz" hükmü üretilebiliyordu — sahte yeşilin en sinsi biçimi.
    """

    def test_duz_metin_icindeki_anis_hukum_sayilmaz(self):
        metin = ("Inceleme tamamlanamadi; beklenen bicim soyleydi "
                 "SONUC: TEMIZ")
        _b, _s, ok = incele.bulgulari_ayikla(metin)
        self.assertFalse(ok, "cümle içindeki anış hüküm sayıldı")

    def test_kendi_satirindaki_hukum_okunur(self):
        _b, s, ok = incele.bulgulari_ayikla("Inceleme bitti.\nSONUC: TEMIZ")
        self.assertTrue(ok)
        self.assertEqual(s.upper(), "TEMIZ")

    def test_hukum_satir_atlayamaz(self):
        """`SONUC:` ile hüküm AYNI satırda olmalı.

        Codex bulgusu (PR #38, sekizinci tur — P0). Sabitleme eklenmişti ama
        aradaki `\\s*` satır sonunu da yiyordu, yani çok satırlı ve ÇELİŞKİLİ
        bir hüküm ilk parçasından okunuyordu:

            SONUC:
            TEMIZ
            DEGIL

        `TEMIZ` alınıp `DEGIL` yok sayılıyor, çıktı bulgusuz olduğunda tutarlı
        ve temiz sayılıyordu. Boşluk sınıfı satır içiyle sınırlandırıldı.
        """
        for metin in ("SONUC:\nTEMIZ\nDEGIL", "SONUC:\nTEMIZ", "SONUC\n: TEMIZ"):
            with self.subTest(metin=metin.replace("\n", "\\n")):
                self.assertFalse(incele.bulgulari_ayikla(metin)[2])

    def test_gercek_sarilmis_cikti_ayristirilir(self):
        """GERÇEK çıktı şekli — kapının canlı yolda çalıştığının kilidi.

        `codex-review.sh` modelin çıktısını SARAR ve hükümden sonra her zaman
        sabit bir dipnot ekler. 2026-08-10'da "hüküm son satır olmalı" kuralını
        koydum ve bu şekli ayrıştırılamaz yaptım: kapı HER PR'da "SONUC satırı
        yok" diyerek kalıcı ENGEL'e düştü. Bulgu Codex'ten geldi; bu test o
        şekli bir daha kırmamak için gerçek gövdeyi birebir taşır.

        Ders: sahte kırmızı burada sahte yeşilden pahalıydı — kapı büsbütün
        işlevsiz kalır ve insana onu atlamayı öğretir.
        """
        govde = ("## Codex incelemesi (risk sinyali)\n\n"
                 "[P2] bin/x.py:1 — ufak not — etki sinirli\n"
                 "SONUC: 1 bulgu (en yuksek: P2)\n\n"
                 "---\n"
                 "Bu bir capraz-vendor risk sinyalidir, makine kaniti "
                 "degildir. Merge kosulu: CI yesil + insan karari.")
        b, hukum, ok = incele.bulgulari_ayikla(govde)
        self.assertTrue(ok, "gerçek sarılmış çıktı ayrıştırılamadı")
        self.assertEqual(len(b["P2"]), 1)
        self.assertTrue(incele.tutarli_mi(b, hukum))

    def test_hukumden_sonra_bos_satir_sorun_degil(self):
        # Sondaki boşluk biçimsel; hükmü geçersiz kılmaz.
        _b, s, ok = incele.bulgulari_ayikla("rapor\nSONUC: TEMIZ\n\n  \n")
        self.assertTrue(ok)
        self.assertEqual(s.upper(), "TEMIZ")

    def test_bosluk_girintili_hukum_de_okunur(self):
        # Girinti biçimsel bir ayrıntıdır, hükmü geçersiz kılmaz.
        _b, s, ok = incele.bulgulari_ayikla("rapor\n   SONUC: TEMIZ")
        self.assertTrue(ok)
        self.assertEqual(s.upper(), "TEMIZ")


class TutarlilikTest(unittest.TestCase):
    """P1 · incele.py:79 — herhangi bir SONUC metni geçerli sayılıyordu."""

    def test_temiz_diyip_bulgu_listeleyen_cikti_tutarsiz(self):
        b = {"P0": ["yetki yok"], "P1": [], "P2": []}
        self.assertFalse(incele.tutarli_mi(b, "TEMIZ"))

    def test_bulgu_var_diyip_hic_listelemeyen_cikti_tutarsiz(self):
        self.assertFalse(incele.tutarli_mi(TEMIZ, "2 bulgu (en yuksek: P0)"))

    def test_turkce_noktali_i_ile_yazilan_hukum_de_okunur(self):
        """`TEMİZ` ile `TEMIZ` aynı hükümdür — kapı kendi dilini okumalı.

        Ölçüm 2026-08-09 (PR #37): Codex hükmü `TEMİZ` yazdı, bulgu listesi
        boştu ve kapı yine de ENGEL verdi. Sebep tek karakter: Türkçe noktalı
        İ, `.upper()` altında ASCII I'ya DÖNÜŞMEZ, yani `"TEMIZ" in "TEMİZ"`
        False'tur. Hüküm okunamamış sayılıp "tutarsız" dalına düşüyordu.

        Sahte kırmızı, sahte yeşil kadar zararlıdır — ikisi de kanıtı bozar
        ve tekrarlayan sebepsiz ENGEL, kapıyı elle atlamayı öğretir.
        """
        self.assertTrue(incele.tutarli_mi(TEMIZ, "TEMİZ"))
        self.assertTrue(incele.tutarli_mi(TEMIZ, "temİz"))
        # Fail-closed tarafı korunur: İ'li hüküm bulguyu görünmez yapamaz.
        b = {"P0": ["yetki yok"], "P1": [], "P2": []}
        self.assertFalse(incele.tutarli_mi(b, "TEMİZ"))

    def test_olumsuz_hukum_temiz_sayilmaz(self):
        """`TEMİZ DEĞİL` temiz DEĞİLDİR — hüküm alt dize olarak aranamaz.

        Codex bulgusu (PR #38). `"TEMIZ" in hukum` alt dize araması, olumsuz
        hükmü olumlu sanıyordu: `TEMIZ DEGIL` + ayrıştırılamamış bulgu listesi
        = "tutarlı ve temiz" → `auto` riskli PR otomatik birleşebilirdi.

        Bu, kapının verebileceği en pahalı hatadır (sahte yeşil) ve ASCII
        biçimde main'de ZATEN vardı; noktalı İ onu Türkçe metinde tesadüfen
        maskeliyordu. Hüküm artık baştan sona eşleşiyor.
        """
        for hukum in ("TEMİZ DEĞİL", "TEMIZ DEGIL", "temiz degil",
                      "TEMIZ OLMAYABILIR"):
            with self.subTest(hukum=hukum):
                self.assertFalse(incele.tutarli_mi(TEMIZ, hukum))

    def test_olumsuz_hukum_sayi_tasisa_da_temiz_sayilmaz(self):
        """Sayısal dal, olumsuz hükmü sayı taşıdığı için geçerli sayamaz.

        Codex bulgusu (PR #38, üçüncü tur). `re.search` sayıyı METNİN HER
        YERİNDE arıyordu: `SONUC: TEMİZ DEĞİL — 0 bulgu` + sıfır ayrıştırılmış
        bulgu = "tutarlı" → auto risk + yeşil CI'da OTOMATİK BİRLEŞME.

        Hüküm tanınan iki biçimden biri olmalı: ya baştan sona `TEMIZ`, ya da
        BAŞTAN itibaren `<sayı> bulgu`. Tanınmayan hüküm tutarsızdır (ENGEL).
        """
        for hukum in ("TEMİZ DEĞİL — 0 bulgu", "temiz degil, 0 bulgu",
                      "reddedildi 0 bulgu", "belirsiz — 0 bulgu"):
            with self.subTest(hukum=hukum):
                self.assertFalse(incele.tutarli_mi(TEMIZ, hukum))

    def test_taninmayan_hukum_bulgu_varken_bile_tutarsiz(self):
        """Okunamayan hüküm, bulgu listelense bile geçerli sayılamaz.

        Codex bulgusu (PR #38, dördüncü tur — P0). Fallback `sayi > 0` idi:
        tek bir `[P2]` bulgusu + `SONUC: TEMIZ DEGIL` "tutarlı" sayılıyordu.
        P2 merge'i durdurmadığı için `auto` riskli PR otomatik birleşirdi —
        hüküm açıkça "temiz değil" dediği hâlde.

        Bu deponun kendi kuralı burada da geçerli: "okunamadı" ile "temiz"
        aynı şey değildir. Tanınan iki biçim dışındaki her hüküm ENGEL'dir.
        """
        for bulgular in (TEMIZ, {"P0": [], "P1": [], "P2": ["ufak"]},
                         {"P0": ["ciddi"], "P1": [], "P2": []}):
            for hukum in ("TEMIZ DEGIL", "BELIRSIZ", "0 BULGU DEGIL",
                          "gozden gecirilemedi"):
                with self.subTest(hukum=hukum, n=sum(map(len, bulgular.values()))):
                    self.assertFalse(incele.tutarli_mi(bulgular, hukum))

    def test_temiz_hukmunu_olumsuzlayan_simge_kabul_edilmez(self):
        """`TEMIZ ❌` temiz değildir — `\\W*` fazla cömertti.

        Codex bulgusu (PR #38, beşinci tur — P0). Sondaki noktalamayı serbest
        bırakmak için `\\W*` yazmıştım; o desen TÜM sözcük-dışı karakterleri
        kabul ediyor, yani anlamı TERSİNE çeviren simgeyi de. Hoşgörü yalnız
        anlamsız noktalama için olmalı, hükmü değiştiren işaret için değil.
        """
        for hukum in ("TEMIZ ❌", "TEMİZ ✗", "TEMIZ —", "TEMIZ ?"):
            with self.subTest(hukum=hukum):
                self.assertFalse(incele.tutarli_mi(TEMIZ, hukum))

    def test_sifir_bulgu_iddiasi_oncelik_belirtemez(self):
        """`0 BULGU (en yuksek: P0)` kendi içinde çelişir.

        Codex bulgusu (PR #38, beşinci tur — P0). Sayı doğrulanıyordu ama
        parantezdeki ÖNCELİK İDDİASI hiç denetlenmiyordu. Hüküm hem "bulgu
        yok" hem "en yükseği P0" diyebiliyor ve tutarlı sayılıyordu.
        """
        self.assertFalse(incele.tutarli_mi(TEMIZ, "0 bulgu (en yuksek: P0)"))
        # Yalan öncelik iddiası da tutarsızdır (sayı tutsa bile).
        b = {"P0": ["ciddi"], "P1": [], "P2": []}
        self.assertFalse(incele.tutarli_mi(b, "1 bulgu (en yuksek: P2)"))
        self.assertTrue(incele.tutarli_mi(b, "1 bulgu (en yuksek: P0)"))

    def test_nfd_biciminde_yazilan_temiz_hukmu_de_okunur(self):
        """`İ` ayrık birleşen nokta olarak gelirse de temiz sayılmalı.

        Codex bulgusu (PR #38 — P2). `TEMİZ` iki Unicode biçimde yazılabilir:
        NFC'de tek kod noktası (U+0130), NFD'de `I` + birleşen nokta (U+0307).
        Düz karakter değişimi yalnız birincisini görüyordu; ikincisi yine
        "okunamadı" sayılıp sahte ENGEL üretirdi — bu PR'ın çıkış noktasıyla
        aynı hata.
        """
        nfd = "TEMİZ"          # I + birleşen nokta
        self.assertNotEqual(nfd, "TEMİZ", "vaka NFD olmalı")
        self.assertTrue(incele.tutarli_mi(TEMIZ, nfd))

    def test_kucuk_harf_ayrik_noktali_i_de_okunur(self):
        """`temi\u0307z` — küçük `i` + birleşen nokta (Codex bulgusu, P2).

        NFC bunu BİRLEŞTİREMEZ: küçük i + U+0307 için önceden birleştirilmiş
        tek kod noktası yoktur. Yalnız NFC'ye güvenmek bu biçimi "okunamadı"
        sayıp sahte ENGEL üretirdi. Çözüm birleşen noktayı normalizasyonda
        DÜŞÜRMEK — Türkçe bağlamda o nokta yalnız i/I üstünde bulunur.
        """
        self.assertTrue(incele.tutarli_mi(TEMIZ, "temi\u0307z"))
        self.assertTrue(incele.tutarli_mi(TEMIZ, "TEMI\u0307Z"))

    def test_eksik_parantez_ve_sifir_sayi_hukum_sayilmaz(self):
        """Beyaz liste ilan edildiği gibi olmalı — parantez opsiyonel değil.

        Codex bulgusu (PR #38, altıncı tur). `(en yuksek: PX)` opsiyonel
        bırakılmıştı, yani `SONUC: 0 bulgu` geçerli ve tutarlı sayılıyordu.
        Oysa istem "bulgu yoksa TEMIZ yaz" diyor; `0 bulgu` sözleşmede YOK.
        """
        for hukum in ("0 bulgu", "1 bulgu", "2 bulgu", "0 bulgu (en yuksek: P2)"):
            with self.subTest(hukum=hukum):
                self.assertFalse(incele.tutarli_mi(TEMIZ, hukum))
        b = {"P0": [], "P1": [], "P2": ["ufak"]}
        self.assertFalse(incele.tutarli_mi(b, "1 bulgu"))
        self.assertTrue(incele.tutarli_mi(b, "1 bulgu (en yuksek: P2)"))

    def test_devasa_sayi_kapiyi_cokertmez(self):
        """Sınırsız basamak `int()`i patlatıp kapıyı ÇÖKERTİYORDU.

        Codex bulgusu (PR #38, dokuzuncu tur — P1). Python 3.11+ 4300
        basamaktan uzun dizeyi `int()`e çevirmeyi reddediyor (ValueError).
        Desen `\\d*` ile sınırsızdı, yani hüküm 4301 basamak taşırsa
        `tutarli_mi` istisna fırlatıyordu.

        Çökme, fail-closed ENGEL ile AYNI ŞEY DEĞİLDİR: biri "kural
        uygulanamadı" diye karar üretir, diğeri aracı kırar ve operatöre
        traceback gösterir. Bu deponun kendi ayrımı — "araç hatası" ile
        "kural ihlali" karıştırılmaz.
        """
        hukum = "9" * 4301 + " bulgu (en yuksek: P0)"
        self.assertFalse(incele.tutarli_mi(TEMIZ, hukum))
        # Makul üst sınır hâlâ çalışır.
        b = {"P0": ["x"], "P1": [], "P2": []}
        self.assertTrue(incele.tutarli_mi(b, "1 bulgu (en yuksek: P0)"))

    def test_noktalama_tasiyan_temiz_hukmu_kabul_edilir(self):
        # Fazla katı eşleşme yeni bir sahte kırmızı üretmemeli; hoşgörü
        # yalnız anlamsız noktalama ve boşluk için.
        for hukum in ("TEMIZ", "TEMİZ", "TEMIZ.", " temiz ", "temiz."):
            with self.subTest(hukum=hukum):
                self.assertTrue(incele.tutarli_mi(TEMIZ, hukum))

    def test_uyumlu_cikti_tutarli(self):
        b = {"P0": ["x"], "P1": [], "P2": []}
        self.assertTrue(incele.tutarli_mi(b, "1 bulgu (en yuksek: P0)"))
        self.assertTrue(incele.tutarli_mi(TEMIZ, "TEMIZ"))




if __name__ == "__main__":
    unittest.main()
