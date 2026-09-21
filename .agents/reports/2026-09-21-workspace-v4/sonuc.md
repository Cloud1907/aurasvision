# V4 — yapısal arayüz yenilemesi

Kullanıcı V3'ü eski arayüze benzer buldu. 2026-09-21 tarihinde aynı UI
kapsamında yerleşim yenilendi; backend ve proje yönlendirme dosyalarına dokunulmadı.

- 212 px sol menü, 96 px genişlikte etiketli kompakt navigasyona dönüştü.
- Dört büyük metrik kartı yerine kısa durum özeti var.
- Kamera+olay akışı ana sütunda; alarm ve kamera sağlığı ortak sağ yüzeyde.
- Kamera seçimleri büyüdü; açık tema boş görüntü durumu nötr yüzeye taşındı.
- Kamera değişimine FadeContent eklendi; Aurora, GlassIcons ve kart etkileşimleri güçlendirildi.
- Mobilde DOM ve görünür sıra kamera → durum sütunu → olay akışı olarak aynı.

Doğrulama: UI 31 test geçti; V4 testi değişiklik öncesinde kırmızı görüldü.
Build JS 390921 / CSS 49008 bayt; ek bağımlılık yok. Yeni yüzeyler için yedi
kontrast çifti geçti (en düşük 4.82:1). 390/768/1440 px taşma kontrolü ve
iki tema screenshotları incelendi. Son görsel turunda mobil sütun genişliği
ve kamera alanının max-height nedeniyle daralması düzeltildi.

1440 px demo: kamera y=255 px (28 px demo etiketi dahil). Tarayıcı pageerror 0.
Bu tur yalnız frontend düzeni içerdiği için Python paketi yeniden koşulmadı.
Gerçek kamera, NVIDIA/CPU performansı ve üretim yükü ölçülmedi; yerel fixture
kontrolü saha kanıtı değildir. CI/PR/push/dağıtım yapılmadı.

Önce: ../2026-09-21-apple-ui/desktop-light.png.
Sonra: desktop.png, dark.png, mobile.png, tablet.png, preview.png.
Önizleme: http://127.0.0.1:8768/?design=v4 (temsili veriler).
Geri dönüş kopyası: /var/folders/yn/t5zkpqvs1v5f4hbzq6lfhlhh0000gn/T/auras-ui-v4-before-5p1cl7e9.
