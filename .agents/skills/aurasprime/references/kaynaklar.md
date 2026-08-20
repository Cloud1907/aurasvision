# AurasPrime profilinin kaynakları

Rol uydurulmadı; üç meslek tanımının kesişiminden çıkarıldı. Erişim:
2026-08-11.

## Rolün kimliği

- **Right Hand arketipi** — [staffeng.com/guides/staff-archetypes](https://staffeng.com/guides/staff-archetypes/)
  Üst düzey yöneticinin yetkisini ödünç alarak karmaşık organizasyonları
  yönetir; iş, teknoloji, insan ve kültürün kesiştiği yerde çalışır.
  AurasPrime'ın "kullanıcının yetkisiyle hareket eder" özelliği buradan.
  Güven: `doğrulanmış` (birincil kaynak, Will Larson'ın çerçevesi).

- **CTO ile VP Engineering ayrımı** — [ctaio.dev/en/guides/cto-vs-vp-engineering](https://ctaio.dev/en/guides/cto-vs-vp-engineering/)
  CTO ne yapılacağına ve niçin yapılacağına, VP Engineering nasıl
  yapılacağına karar verir. AurasPrime ikisini birden taşır çünkü kullanıcı
  "ne"yi getirir, "niçin"in netleşmesi ve "nasıl"ın dağıtılması ondadır.
  Güven: `ikincil` (rol tanımı literatürü, tek kaynak).

- **İhtiyaç analizi (elicitation)** — [bridging-the-gap.com](https://www.bridging-the-gap.com/elicitation-techniques-business-analysts/)
  Belirsiz isteği netleştirme teknikleri: geri söyleme (paraphrase), somut
  örnek isteme, netleşene dek izleme. Başarısız projelerin çoğunluğunun
  ihtiyaç toplama eksikliğinden kaynaklandığı bulgusu bu literatürden.
  Güven: `ikincil` (meslek pratiği, ölçüm iddiası çapraz doğrulanmadı).

## Yöntem ve hata modelleri

- **Routing deseni, workflow/agent ayrımı, basitlik ilkesi** —
  [anthropic.com/research/building-effective-agents](https://www.anthropic.com/research/building-effective-agents)
  Girdi sınıflandırılıp uzmanlaşmış işleme yönlendirilir. Adımlar tahmin
  edilebiliyorsa ajan değil düz iş akışı kullanılır. "Basitliği koru,
  planı şeffaf göster" ilkeleri buradan.
  Güven: `doğrulanmış` (birinci el mühendislik yazısı).

- **Brief sözleşmesi ve delegasyon hataları** —
  [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
  Her alt görev hedef, çıktı biçimi, araç/kaynak rehberi ve açık sınır
  ister. Belirsiz talimatın alt-ajanlara aynı işi tekrarlattığı ve basit
  sorgu için aşırı ajan açmanın bir hata modeli olduğu burada itiraf edilir.
  Güven: `doğrulanmış` (üreticinin kendi retrospektifi).

## Yerel ders

- **Kapsam kayması** — AurasAgents PR #39 (2026-08-11). "Bir skill ekle"
  işi router revizyonuna dönüştüğü için 16 tur bağımsız inceleme sürdü;
  turların çoğu önceki turun düzeltmesinden doğan kusurları buldu. Kayıt:
  `git log` ve PR #39 yorumları. Güven: `doğrulanmış` (kendi kaydımız).
