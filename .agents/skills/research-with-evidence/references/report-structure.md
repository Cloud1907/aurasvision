# Rapor yapısı — dünya standardı araştırma raporu iskeleti

## İçindekiler
- Neden bu sıra (pyramid principle)
- İskelet (bölüm bölüm)
- Kötü örnek (anti-pattern)
- İyi örnek (aynı soru, düzgün)

## Neden bu sıra

Okuyucu (çoğu zaman karar verecek kurucu) önce **cevabı** ister, sonra
gerekçeyi. Ters piramit: sonuç en üstte, kanıt derinleştikçe aşağıda.
Kimse 40 satır okuyup en sonda "sonuç: A seçeneği" görmek istemez. TL;DR
tek başına okunduğunda karar verilebilmeli; gerisi savunma katmanıdır.

## İskelet

### 1. TL;DR (3 cümle, zorunlu)
- Cümle 1: ne soruldu.
- Cümle 2: ne bulundu (en yüksek güvenli ana bulgu).
- Cümle 3: ne öneriliyor / karar.
- Kaynak gerekmez (aşağısı kaynaklar); ama abartma yok.

### 2. Bulgular (kaynaklı, güven-etiketli)
- Her bulgu ayrı madde/paragraf; en önemliden başla.
- Her biri: iddia + kaynak (dosya:satır / URL / commit) + güven etiketi
  (`doğrulanmış` / `ikincil` / `spekülatif`).
- Çelişen kanıt varsa gizleme — göster ve nasıl tarttığını yaz.
- Karşılaştırma işiyse tablo kullan (seçenek × kriter); her hücre kaynaklı.

### 3. Karar önerisi
- Bulgulardan çıkan aksiyon. Gerekçe yukarıdaki kaynaklara atıf yapar
  ("Bulgu 2 ve 4 nedeniyle...").
- Trade-off'ları açıkça yaz; "her yönden en iyi" nadiren doğrudur.
- Karar sınıfı işiyse (AGENTS.md risk): önerinin risk sınıfını da belirt.

### 4. Açık sorular
- Doğrulanamayan iddialar, eksik kaynaklar, çapraz-doğrulanamayanlar.
- "Bu cevabı sağlamlaştırmak için sonra şuna bakılmalı" listesi.
- Boş bırakma; dürüst araştırmada her zaman en az bir açık uç vardır.

### Meta (opsiyonel, uzun raporda)
- Kapsam: neye bakıldı, neye bakılmadı (yokluk kanıtının sınırı).
- Tarih/commit damgası (bayatlık için).

## Kötü örnek (anti-pattern)

> # Hangi validasyon aracını kullanmalıyız?
>
> Öncelikle mevcut duruma baktım. Repoda bir bin/ klasörü var ve içinde
> çeşitli scriptler bulunuyor. validate.py dosyasını inceledim, oldukça
> kapsamlı görünüyor. Ayrıca make_evidence.py da var. Bunları çalıştırmayı
> denedim. Sanırım validate.py yeterli olabilir çünkü çok şey kontrol
> ediyor gibi görünüyor. Muhtemelen bunu kullanmalıyız.

Sorunlar: karar en sonda ve "sanırım/muhtemelen"; kaynak yok (hangi satır
neyi kontrol ediyor?); "kapsamlı görünüyor" ölçüsüz görüş; kapsam ve güven
belirsiz.

## İyi örnek (aynı soru, düzgün)

> # Hangi validasyon aracını kullanmalıyız?
>
> **TL;DR:** Kernel bütünlüğünü tek komutta doğrulamak için `bin/validate.py`
> yeterli; ayrı bir araca gerek yok. Script skill/profil/form/şema/evidence
> tutarlılığını tek yerde denetliyor ve CI ile pre-push kancasında zaten
> koşuyor. Öneri: `bin/validate.py`'yi kanonik kapı yap.
>
> ## Bulgular
> 1. `validate.py` yedi bağımsız kontrol grubu koşar: skills, profiles,
>    issue form, workflow, evidence roundtrip, AGENTS.md, mekanizmalar
>    (`bin/validate.py:main()`). — `doğrulanmış`
> 2. Aynı doğrulama iki kapıda tekrarlanıyor: pre-push kancası
>    (`bin/hooks/pre-push`, `validate.py` çağrısı doğrulandı) ve CI evidence
>    job'ı (`.github/workflows/evidence.yml`). — `doğrulanmış`
> 3. Script bağımlılığı yalnız PyYAML; harici servis yok
>    (`bin/validate.py:16-19`). — `doğrulanmış`
>
> ## Karar önerisi
> `bin/validate.py` kanonik doğrulama kapısı olarak yeterli (Bulgu 1-2).
> Ek araç bakım yükü getirir, çift kaynak riski yaratır. Risk sınıfı: auto
> (yalnız doğrulama, kod değişmiyor).
>
> ## Açık sorular
> - PyYAML kurulu değilse script exit 2 veriyor; CI ortamında garanti mi?
>   (kurulum adımı doğrulanmadı) — sonraki adım: workflow'daki pip adımına bak.
