---
title: "KVKK / Gizlilik Notları"
type: reference
updated: 2026-06-29
topics: [kvkk, yüz, plaka, retail]
tags: [kvkk, gizlilik, biyometrik]
---

# KVKK / Gizlilik Notları

> Hukuki tavsiye değildir — tasarım kararlarına yön veren mühendislik notudur. Üretim öncesi hukuk danışmanlığı şart.

## Veri Sınıfı
- **Yüz görüntüsü / yüz embedding'i** → KVKK kapsamında **özel nitelikli kişisel veri (biyometrik)**.
- **Plaka** → kişisel veri (araç sahibiyle ilişkilendirilebilir).
- İsimle/kimlikle eşleştirme yapıldığı anda işleme ağırlaşır; **açık rıza + aydınlatma metni** gündeme gelir.

## Risk Dereceleri (düşükten yükseğe)
| İşleme | Risk | Şart |
|---|---|---|
| Anonim sayım / ısı haritası / footfall | Düşük | Aydınlatma tabelası |
| Anonim demografi (yaş/cinsiyet, kimlik yok) | Düşük-orta | Aydınlatma; kimliklendirme yok |
| Tekrar ziyaretçi (anonim ID) | Orta (gri alan) | Hukuki görüş |
| İsimli yüz tanıma (VIP/kara liste/PDKS) | Yüksek | Açık rıza + aydınlatma + saklama politikası + alternatif giriş |
| Plaka takip/rota | Orta-yüksek | Amaç sınırlaması, saklama süresi, aydınlatma |

## Tasarım İlkeleri (manifest forbidden ile uyumlu)
1. **Edge'de işle** — yüz/plaka verisini mümkünse cihazdan dışarı çıkarma; merkeze sadece embedding/metrik.
2. **Görüntü saklama** — ham kareyi kalıcı tutma; sadece anonim sonuç + (gerekiyorsa) embedding.
3. **Retail varsayılanı anonim** — kimliklendirme opt-in ve ayrı KVKK kapısına bağlı.
4. **Erişim kontrolünde liveness zorunlu** + kart/PIN fallback (cihaz arızası/tanınmama için).
5. **Secret/PII** kodda değil; bağlantı string'i ve anahtarlar .env/secret yönetiminde.
6. **Saklama süresi** ve **amaç sınırlaması** baştan tanımlı; süre dolunca otomatik silme.
