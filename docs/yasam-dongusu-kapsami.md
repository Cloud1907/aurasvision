# Yaşam döngüsü kapsam haritası — sistem neyi zorlar, neyi zorlamaz

**Tarih:** 2026-08-07 · **Ölçüm reposu:** AurasAgents (kernel) + 4cast (amiral)
**Durum:** Tasarımın ikinci ekseni. Birinci eksen
`VIBE_CODING_TASARIM_TEMMUZ_2026.md` (yönetişim).

## Neden bu belge var

`VIBE_CODING_TASARIM_TEMMUZ_2026.md` tek soruyu cevaplıyordu: **"agent
çıktısına nasıl güvenirim?"** O sorunun doğal cevapları kanıt, kapı ve
deterministik kontroldür — ve deterministik kontrol en kolay doğruluk ile
güvenlik tarafında kurulur.

Sonuç: sistem yazılım yaşam döngüsünün **ortasına** yığıldı. Başı (*ne
yapmalı, nasıl görünmeli*) ve sonu (*çalışıyor mu, kullanılıyor mu*) hiç
çerçeveye girmedi.

Ölçüm (2026-08-07): tasarım belgesinde "UX" **1 kez** geçiyor, o da risk
seviyelerinin nasıl anlatılacağı hakkında. §9 "Bilinçli olarak
yapılmayanlar" listesindeki 6 maddenin **hiçbiri** tasarım/UX/operasyon
değil. Yani bu alanlar **ertelenmedi — hiç düşünülmedi.**

Bu belge o boşluğu kapatmaz; **adını koyar.** Kapsam sınırını gizleyen bir
sistem, kapsamı dar olan sistemden daha tehlikelidir: kullanıcı korunduğunu
sanır.

## Kapsam haritası

| # | Aşama | Kapsam | Ölçülen durum |
|---|---|---|---|
| 1 | Keşif | ✗ yok | Problem tanımı, kullanıcı araştırması, rakip analizi — hiçbir mekanizma yok |
| 2 | Ürün tanımı | ◐ kısmi | Issue Form: hedef · EARS kriter · kapsam · ön risk · zorunlu kanıt. Mikro işte atlanabilir |
| 3 | Tasarım | ✗ yok | `designing-interfaces` skill'i var (4 referans) ama **kapı yok**; akış/UI/a11y denetlenmiyor |
| 4 | Mimari | ◐ kısmi | 4 ADR var; ADR **zorunluluğu** kapıda değil, NFR hedefi (yanıt süresi, eşzamanlılık) hiç yok |
| 5 | Uygulama | ✓ kapı var | Kalite ratchet (`bin/kalite.py`) · test-önce (`check_test_first`) · Codex risk sinyali |
| 6 | Doğrulama | ◐ kısmi | Test + secret güçlü; **perf, a11y, görsel regresyon yok**. `contrast_check.py` yazılı ama bağlı değil |
| 7 | Sürüm | ✓ kapı var | Deploy `evidence` yeşiline bağlı · tarihli yedek · sağlık kontrolü |
| 8 | Operasyon | ✗ yok | APM/alarm/SLO yok. 4cast deploy'unda **2 satır** sağlık kontrolü; 22 dosyada `ILogger` var ama toplama katmanı yok |
| 9 | Ölçme | ✗ yok | 4cast `package.json`'da **0 analitik bağımlılığı**. Hangi ekran kullanılıyor, nerede bırakılıyor — veri yok |
| 10 | Bakım | ◐ kısmi | Ratchet · `memory_hygiene` · `dep_audit`; doküman bayatlığı denetimi yok |

**Toplam: 2 tam · 4 kısmi · 4 hiç.**

## İki tür eksik — karıştırmamak şart

### A) Ölçülebilir (kapıya bağlanabilir)

Bugünkü ratchet mantığıyla kurulabilir: mevcut ihlal dondurulur, büyümesi
bloklanır.

| Aşama | Kurulabilecek kapı | Tahmini |
|---|---|---|
| 8 | Hata izleme (Sentry/OTel) + uptime alarmı | 1 gün |
| 9 | Ürün analitiği — ekran kullanımı, terk noktası | 1 gün |
| 6 | a11y taraması (axe) + kontrast (`contrast_check.py` zaten yazılı) | yarım gün |
| 6 | Görsel regresyon (Playwright `toHaveScreenshot`) | yarım gün |
| 4 | NFR hedefi → ölçülebilir eşik (p95 yanıt süresi, eşzamanlı kullanıcı) | yarım gün |
| 10 | Doküman bayatlığı (kod değişti, doküman değişmedi) | 2 saat |

### B) Ölçülemez (kapıya bağlanmamalı)

Keşif doğruluğu (*problem doğru mu*), estetik yargı (*premium duruyor mu*),
bilgi mimarisi (*bu akış mantıklı mı*), önceliklendirme (*bu mu yapılmalı*).

Bunları mekanizmaya çevirmeye çalışmak **sahte kesinlik** üretir: yeşil bir
kapı, kötü bir tasarımı onaylamış gibi görünür. Bu alanlar proje sahibinin
yargısı ve `designing-interfaces` / `research-with-evidence` skill'lerinin
tavsiye alanı olarak kalır — ve bunun böyle olduğu **açıkça** yazılır.

## Öncelik — neden bu sırayla

1. **Operasyon (aşama 8).** Deploy kapısı kuruldu ama deploy *sonrası*
   görülmüyor. Üretimde bir hata saatlerce yaşayabilir ve hiçbir mekanizma
   haber vermez — kullanıcı arayana kadar. En yüksek risk burada.
2. **Ölçme (aşama 9).** Aşama 1'i (*ne yapmalı*) besleyebilecek tek girdi.
   Kullanım verisi olmadan önceliklendirme tahmindir.
3. **Doğrulama genişletmesi (aşama 6).** a11y + görsel regresyon. Kaliteyi
   korur ama kimse ölmez.

Not: bu sıra 2026-08-07'de **değiştirildi**. Önceki öneri "önce a11y"ydi;
harita çıkarıldıktan sonra kör uçuşun (aşama 8) daha yüksek risk taşıdığı
görüldü. **Önce göz, sonra kalite.**

## Bu belgenin bakımı

Kapsam değiştikçe bu tablo bayatlar. Bir aşamaya kapı eklendiğinde satırı
güncellenir; güncellenmemesi belgeyi yanlış-güven kaynağına çevirir.
`bin/validate.py` belgenin varlığını ve `AGENTS.md`'den referans verildiğini
doğrular — **içeriğin güncelliğini doğrulayamaz.** Bu, bu belgenin kendi
kapsam sınırıdır.
