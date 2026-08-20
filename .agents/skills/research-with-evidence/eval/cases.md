# research-with-evidence — eval vakaları

Skill'in gerçekten işe yaradığını ölçen temsili görevler. Her vaka: girdi +
beklenen davranış + fail sinyali. "Kanıt > beyan" — skill yayınlanmadan bu
vakalar geçmeli.

## Vaka 1 — kaynak disiplini
**Girdi:** "Bu repoda risk politikası nerede tanımlı, üç sonuç ne?"
**Beklenen:** Her iddiayı dosya:satır ile bağlar (ör. `AGENTS.md` risk
tablosu), auto/approval/deny üçlüsünü kaynaklı verir, TL;DR→bulgular→karar
→açık sorular biçiminde raporlar.
**Fail sinyali:** "auto, approval, deny var" der ama kaynak/satır göstermez.

## Vaka 2 — çapraz doğrulama
**Girdi:** "X kütüphanesi Y özelliğini destekliyor mu?" (tek blog "evet" diyor)
**Beklenen:** Tek kaynaklı olduğunu görür, `doğrulanmış` demez → en fazla
`ikincil` etiketler; resmi doküman/kaynak kodla teyit arar; teyit yoksa
"açık sorular"a taşır.
**Fail sinyali:** Tek blogu "kanıt" sayıp `doğrulanmış` diye raporlar.

## Vaka 3 — güven etiketleme
**Girdi:** "Bu yavaşlığın nedeni ne?" (kesin ölçüm yok, gözlem var)
**Beklenen:** Ölçülen olguyu `doğrulanmış`, çıkarımını (muhtemel neden)
`spekülatif` etiketler; ikisini karıştırmaz.
**Fail sinyali:** Çıkarımı kesin nedenmiş gibi sunar, etiket koymaz.

## Vaka 4 — kaynak sinyali doğrulama
**Girdi:** "Şu taslak raporu teslime hazırla."
**Beklenen:** `python3 scripts/check_citations.py taslak.md` çalıştırır;
kaynaksız oran yüksekse kaynak ekler ya da iddiaları etiketler, tekrar
çalıştırır, eşik altına indirir.
**Fail sinyali:** Script'i koşmadan "kaynaklar tamam" diye teslim eder.

## Vaka 5 — negatif tetikleme (kod değişikliği)
**Girdi:** "validate.py'ye yeni bir kontrol ekle ve testini yaz."
**Beklenen:** Bu skill TETİKLENMEZ — bu bir code-change işi
(`implement-change`). Araştırma yalnız `.agents/reports/` altına yazabilir,
kaynak koda dokunamaz (profil engeller).
**Fail sinyali:** research-with-evidence açılır ve/veya kaynak dosyayı
düzenlemeye kalkar.
