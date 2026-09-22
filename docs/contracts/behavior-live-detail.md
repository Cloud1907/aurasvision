# Canlı telefon ve sigara kaçırma düzeltmesi

Kapsam: davranış hattı, kaynak seçimi, ilgili testler ve yapılandırma.

- Telefon veya sigara açıkken ana akış tercihi kaynak seçimine uygulanır.
- Kişinin elinde zaman içinde doğrulanan telefon, kulakta olmasa da telefon kullanımı alarmı üretir.
- Masadaki telefon, boş el ve tek karelik nesne tespiti alarm üretmez.
- Sigara zamansal kuralları korunur; telefon ve sigara aynı kişide bağımsız değerlendirilir.
- Kişi kırpması sınırlandırılır, tespitler kare koordinatlarına döner; eski kutular süresiz kullanılmaz.

Doğrulama: kaynak seçimi ve davranış regresyon testleri; yerel kayıt üzerinde önce/sonra yeniden analiz; canlı worker kaynak ve sağlık kontrolü. Kamera görüntüleri depoya eklenmez.

Plan: testte hatayı üret → kaynak/telefon doğrulamasını düzelt → kayıtla ölç → canlı işleyiciyi yeniden başlat ve sağlık kontrolü.

Sonuç: Üç regresyon testi önce başarısız oldu, düzeltmeden sonra geçti.
148 Python ve 12 JavaScript testi geçti. Yerel kayıt yeniden analizinde
telefon ve sigara alarmı üretildi. Üç negatif klipte alarm yok; bir sigara
ön uyarısı var. İlk canlı açılışta geçici CUDA hatası görüldü; ikinci açılışta
201 ve 207 ana akışta yaklaşık 4 fps işlemeye döndü. Bu GPU başlatma hatasının
kök nedeni bu değişiklikte giderilmiş sayılmaz.

RTSP zamanının geriye dönmesinde kamera takip geçmişi yenilenir; eski PTS'ye
kadar analiz durmaz. Davranış hızı kamera bazında loglanır. Son canlı ölçümde
201 davranış hattı yaklaşık 1–2,3 fps aralığında çalıştı. 1 fps kayıt deneyinde
telefon alarmı oluştu, sigara ön uyarıda kaldı; düşük hızda kısa sigara hareketi
kaçırma riski sürer. 4 fps kayıt deneyinde her iki alarm da doğrulandı.
