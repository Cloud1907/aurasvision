# Brief sözleşmesi — devredilen her işin taşımak zorunda olduğu dört alan

Kaynak ders: Anthropic'in çok-ajanlı araştırma sistemi yazısı. Erken
sürümlerde lider ajan "yarı iletken açığını araştır" gibi talimatlar
veriyordu; alt-ajanlar ya görevi yanlış yorumluyor ya birebir aynı işi
tekrarlıyordu. Çözüm, görev tanımını sözleşmeye bağlamak oldu.

## Dört alan

### 1. Hedef
Ne başarılacak — çıktı değil **sonuç** cümlesi.

- Kötü: "fatura ekranına bak."
- İyi: "Faturanın müşteriye ulaşma süresini ölçülebilir biçimde kısalt;
  bugünkü gecikmenin nerede oluştuğunu bul."

### 2. Çıktı biçimi
Elime ne gelecek? Rapor mu, kod mu, karar mı, liste mi? Uzunluk ve biçim
belirsizse iş iki kez yapılır.

- İyi: "Dosya:satır kanıtlı en fazla 5 maddelik bulgu listesi + tek cümlelik
  öneri."

### 3. Kaynak ve araç sınırı
Nereye bakılacak, nereye bakılmayacak. Hangi araçlar serbest, ağ açık mı,
hangi dizinler kapsam içinde.

- İyi: "Yalnız `Revenue.API` ve `frontend/src/fatura` altına bak; veritabanı
  şemasına dokunma; ağ kapalı."

### 4. Kapsam dışı
Açıkça yapılmayacaklar. Bu alan boş bırakılırsa kapsam kayması başlar —
en pahalı hata modelimiz.

- İyi: "Bu turda düzeltme YAPMA, yalnız teşhis. Şema değişikliği ayrı iştir."

## Kontrol

Devretmeden önce dördünü de yazdın mı? Biri eksikse iş henüz devredilebilir
değildir. Eksik alanı doldurmak, yanlış yapılmış işi geri almaktan ucuzdur.

## Ölçek notu

Brief'in ağırlığı işin ağırlığına eşit olmalı. Tek satırlık düzeltme için
dört başlıklı sözleşme yazmak, sözleşmenin kendisini israfa çevirir — o
durumda iş zaten devredilmez, doğrudan yapılır.
