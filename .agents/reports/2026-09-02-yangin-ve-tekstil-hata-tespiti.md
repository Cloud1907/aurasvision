# Dünyadaki en iyi çözümler: (1) yangın/duman tespiti · (2) iplik-tekstil fabrikasında hata tespiti

**Tarih:** 2026-09-02 · **Repo HEAD:** `a9bbba5` · **Sınıf:** research · **Risk:** auto (yalnız araştırma; kod değişmedi)
**Kapsam:** Ticari lider ürünler, geçerli standartlar/sertifikalar, bağımsız performans ölçümleri, açık veri setleri ve model zemini. Fiyatlandırma, Türkiye mevzuatı ve tedarikçi teklifleri kapsam DIŞI (bkz. Açık sorular).

---

## TL;DR

Sorulan: dünyada en iyi çalışan yangın dedektörü ve bir iplik fabrikasında hata bulan sistem.
Bulunan: **her ikisinde de "en iyi" tek bir ürün değil, bir gecikme/aşama merdivenidir** — yangında kıvılcım tespiti (100–300 ms) → aspirasyonlu duman (ASD) → video duman (saniyeler) → alev dedektörü (20 sn+) → sprinkler (4–8 dk) şeklinde sıralanır ve kamera-tabanlı tespit bu merdivenin ortasında, **EN 54 kapsamı dışında** durur; tekstilde ise iplik hatası tespiti Uster/Loepfe'nin sensörlü iplik temizleyicileriyle fiilen kapalı bir pazar, kamera-tabanlı sistemin gerçek boşluğu **kumaş muayenesi ve ring salonu görsel izleme**dir.
Öneri: AurasVision için yangın tarafında "sertifikalı yangın alarmı" değil **erken uyarı + kanıt katmanı** hedefle; tekstil tarafında iplik temizleyiciyle yarışma, **ring salonu görsel izleme + kumaş muayene + kıvılcım/yangın erken uyarı** üçlüsüne gir.

---

# BÖLÜM A — Yangın ve duman tespiti

## A1. Çerçeve: "en iyi dedektör" bir gecikme merdivenidir

Firefly'ın kendi teknik dokümanındaki zaman ekseni, farklı teknolojilerin aynı olaya ne zaman müdahale ettiğini tek grafikte veriyor: kıvılcım tespiti **100–300 ms (yangın öncesi)**, hızlı bastırma **0,3–5 sn**, alev dedektörlü konvansiyonel bastırma **20 sn → dakikalar**, sprinkler/su sisi **~4–8 dakika** (https://firefly.se/wp-content/uploads/2022/12/Firefly_SparkDetect_ver.1.2_en-1.pdf, erişim 2026-09-02). — `doğrulanmış` (üreticinin birincil teknik dokümanı; ancak üreticinin kendi karşılaştırması olduğu için rakip teknolojilere ait uçlar `ikincil` sayılmalı)

Bu merdiven kritik çünkü soruyu değiştiriyor: "en iyi dedektör hangisi" değil, **"hangi aşamada yakalamak istiyorum"**. Bir iplik fabrikasında kanal içindeki kızgın partikülü 200 ms'de yakalayan sistemle, salonda yükselen dumanı 15 saniyede yakalayan kamera birbirinin rakibi değil, ardışık katmanlarıdır. — `[yorum]`

Aspirasyonlu duman tespiti (ASD/VESDA) bu merdivende "görünür duman oluşmadan önce" bandında yer alır: EN 54-20 ASD'leri üç duyarlılık sınıfına ayırır ve Class A "görünür duman oluşmadan tespit" seviyesidir (https://eurofyre.co.uk/news/understanding-en54-20-aspirating-smoke-detection-sensitivity-classes/, erişim 2026-09-02; ürün tarafı: https://xtralis.com/page/1071/vesda-e-aspirating-smoke-detection). — `ikincil` (iki kaynak var ama biri satıcı, biri distribütör-editöryel; bağımsız ölçüm görülmedi)

## A2. Regülasyon gerçeği — kamera tabanlı tespit EN 54 kapsamında DEĞİL

Bu, ürünleşme açısından bulguların en önemlisi. Video tabanlı yangın tespiti EN 54 standardında karşılığı olmayan bir teknoloji; Bosch/VdS sertifikasyon röportajında açıkça "video tabanlı yangın tespiti henüz EN 54 kapsamında değil, ISO'nun aktif çalışma maddesi; FM3232 ve UL268B halihazırda ele alıyor" deniyor (https://git-sicherheit.de/en/topstories/interview-with-bosch-and-vds-on-the-certification-for-video-fire-detection-products). — `doğrulanmış` (FIA Fact File 90 bağımsız olarak aynı boşluğu tarif ediyor, aşağıda)

Uluslararası standart yolu şöyle ilerledi: ISO/TS 7240-29 **Haziran 2017**'de Teknik Şartname (TS) olarak yayımlandı — tam standart değil, çünkü ISO/TC21/SC3 test yöntemlerinin doğrulanmasının tamamlanmadığına karar verdi (FIA Fact File 90, s.3-4, https://www.fia.uk.com/static/f3c3a6eb-d620-4904-89c8213a6906da63/FACT-FILE-90-Video-Fire-Detectors-and-Detection-Systems.pdf); tam standart **ISO 7240-29:2024** olarak Ocak 2024'te yayımlandı (https://www.iso.org/standard/83347.html). — `doğrulanmış`

FM Approvals, dünyada video görüntü yangın dedektörü (VIFD) standardını ilk geliştiren kuruluş: **Approval Standard 3232**, tam ölçekli yangın testleri kullanır (https://www.fmapprovals.com/-/media/Feature/Approval-Standards/3232-pdf.pdf). ISO WG24 taslağı hazırlarken FM 3232 ve UL 268B içeriğinden beslendi (FIA Fact File 90, s.5). — `doğrulanmış` (iki bağımsız kaynak: FM'in kendi standardı + FIA'nın bağımsız anlatımı)

Sertifikalı ürünlerin durumu:

| Ürün | Sertifika | Tarih / kayıt | Kaynak |
|---|---|---|---|
| Bosch AVIOTEC | VdS onayı — dünyada ilk video duman tespiti | 16 Kasım 2017, no. **G217090** | https://www.securityworldmarket.com/int/Newsarchive/first-ever-video-smoke-detection-gains-vds-approval1 |
| Araani SmokeCatcher | BOSEC + CNPP; BOSEC **ISO/TS 7240-29:2017** temelinde verildi | 2019 | https://www.araani.com/en/about-us/news-events/25-06-2019-belgische-rookdetectie-camera-behaalt-dubbele-primeur/ |
| Araani FireCatcher | BOSEC + CNPP, **birincil** yangın tespiti olarak | — | https://www.araani.com/en/solutions/fire-safety/firecatcher/ |
| Firefly kıvılcım tespiti | FM sertifika no. **3060012**, VdS onay no. **S6990002** | — | https://firefly.se/wp-content/uploads/2022/12/Firefly_SparkDetect_ver.1.2_en-1.pdf |

Sonuç: sertifikasız bir video tespit ürünü **yasal olarak zorunlu yangın alarmının yerine geçemez**; Araani'nin sertifikaları tam da bu rolü üstlenebilmek için alınmış (https://www.axis.com/customer-story/analytics-fire-detection). Bu, pazara giriş için mühendislik değil, **belgelendirme kapısıdır**. — `doğrulanmış`

## A3. Dürüst performans rakamı — pazarlama ile bağımsız ölçüm arasındaki uçurum

FIA'nın BRE ile yürüttüğü bağımsız araştırma projesi, video duman dedektörlerini (VSD) kontrollü koşullarda ölçtü ve şu sonucu yayımladı: **arka planla kontrast eden küçük yükselen duman hacimlerinde ortalama %58 başarı**, benzer renkli arka planlarda **~%52** (FIA Fact File 90, s.10, https://www.fia.uk.com/static/f3c3a6eb-d620-4904-89c8213a6906da63/FACT-FILE-90-Video-Fire-Detectors-and-Detection-Systems.pdf). — `doğrulanmış` (bağımsız test kuruluşu ölçümü; satıcı beyanı değil)

Aynı belge nedenini de veriyor: "beyaz dumanı beyaz arka planda tespit etmek neredeyse imkânsızdır" ve duman görünürlüğü "arka plana ve aydınlatmanın şiddetine (ve açısına) yüksek oranda bağımlı" bulundu; testlerin geceleri yapılması gerekti ve rüzgârlı günlerden kaçınıldı (FIA Fact File 90, s.10). — `doğrulanmış`

Bunu satıcı beyanıyla yan yana koymak gerekiyor: Araani'nin 12 m yüksekliğinde bir binada yaptığı canlı testte SmokeCatcher **15 saniyede** alarm verirken tavana monte duman dedektörleri hiçbir şey algılamadı (https://www.axis.com/customer-story/analytics-fire-detection). İki bulgu çelişmiyor — birbirini tamamlıyor: **VSD'nin üstünlüğü duyarlılıkta değil, dumanın tavana ulaşamadığı geometrilerde** (yüksek hacim, dış mekân, açık alan). Karar bu ayrıma dayanmalı. — `[yorum]` (iki kaynağın uzlaştırılması; kendi çıkarımım)

Standardın kendi sınırları da açık yazılmış (hepsi FIA Fact File 90, https://www.fia.uk.com/static/f3c3a6eb-d620-4904-89c8213a6906da63/FACT-FILE-90-Video-Fire-Detectors-and-Detection-Systems.pdf):
- ISO/TS 7240-29 **yanlış alarm testi tanımlamıyor**; yalnız "dedektörler istenmeyen alarma yol açan olgulardan bağışık olacaktır" diyen bir madde ve opsiyonel, tanımsız test imkânı içeriyor (FIA Fact File 90, s.6). — `doğrulanmış`
- Aydınlatma aralığı 15–10.000 lux; dış mekân üst sınırı çelişkili biçimde 20.000 lux'te test ediliyor (a.g.e., s.6). — `doğrulanmış`
- Zorunlu arıza modları: lens odak kayması, lens kirlenmesi, tam obskürasyon, düşük ışık (a.g.e., s.5-6). — `doğrulanmış`
- Performansın ortama bağımlılığı o kadar belirleyici ki ISO ayrı bir **kurulum standardı ISO/TS 7240-30** hazırlamak zorunda kaldı; maskelenen bölgelerden yayılan dumanın da tespit edilmesi ve **saha performans testi yapılması** şartı getiriliyor (a.g.e., s.11). — `doğrulanmış`

**Bu bölümün tek cümlelik dersi:** video yangın tespitinde ürünü belirleyen şey model değil, kurulum geometrisi + arka plan + aydınlatma + saha doğrulamasıdır. — `[yorum]`

## A4. Ticari lider haritası

| Çözüm | Kategori | Ayırt edici | Kaynak |
|---|---|---|---|
| **Bosch AVIOTEC 8000i IR** | Kamerada gömülü VSD | 4 MP + entegre IR aydınlatma, 0 lux'te "tam karanlıkta" tespit; derin öğrenme; VdS onaylı; EN54 TF1–TF8 test yangınlarında tespit iddiası | https://www.boschbuildingtechnologies.com/lifesafetysystems/en/news-events/ai-video-based-fire-detection/ · https://www.asmag.com/suppliers/productcontent.aspx?co=boschsecuritysystems&id=33507 |
| **Araani SmokeCatcher / FireCatcher** | Axis kamerada çalışan analitik | BOSEC+CNPP ile **birincil** dedektör rolü; atık tesisi, kimya, yüksek hacim odaklı | https://www.araani.com/en/solutions/fire-safety/firecatcher/ |
| **Fire Rover** | Termal tespit + uzaktan bastırma | FLIR A310f termal kamera (320×240, ±2 °C) + uzaktan operatör + köpük; tespit ile müdahale aynı üründe | https://www.waste360.com/product-news/fighting-waste-recycling-industrial-fires-over-the-internet · https://firerover.com/industries/wasteandrecycling/ |
| **FLIR/Teledyne termal (A50 vb.)** | Kalibre sıcaklık ölçümü | Duman oluşmadan sıcaklık eşiği; atık/geri dönüşüm standardı | https://www.flir.com/instruments/fire-prevention/waste-and-recycling/ |
| **Xtralis VESDA / VESDA-E** | Aspirasyonlu (ASD) | EN 54-20 Class A; kamera değil ama "en erken uyarı" ölçütü | https://xtralis.com/page/1071/vesda-e-aspirating-smoke-detector-vlc |
| **Firefly / Arosa / Flamex / Argus** | Kanal içi kıvılcım tespiti | 100–300 ms; FM+VdS; tekstil/ahşap/biyoyakıt | https://firefly.se/technology/spark-detection-system/ · https://arosasystems.com/spinning-nonwovens-recycling/ |
| **Pano AI** | Açık alan / orman | 17 ABD eyaleti + Avustralya/Kanada'da 50 milyon akr izleme | https://www.wvia.org/news/environment/2026-05-21/ai-is-watching-for-wildfires-across-the-drought-stricken-west |
| **ALERTCalifornia** | Açık alan / orman | ~1.240 AI kamera; **2025'te 915 yangını halktan önce tespit** (Cal Fire istihbarat şefi beyanı) | https://www.capradio.org/articles/2026/05/04/states-across-the-wildfire-prone-western-us-are-using-ai-for-early-detection/ |

ALERTCalifornia'nın 915 rakamı bir kurum yetkilisinin beyanı olduğu ve bağımsız denetim raporu görülmediği için `ikincil` sayılmalı; ancak aynı iddia birden fazla haber kuruluşunun bağımsız muhabirliğinde tekrar ediyor (capradio, wvia, klcc — NPR ağı, muhtemelen **tek orijin**, dolayısıyla çapraz doğrulama sayılmaz). — `ikincil`

## A5. Kendi modelini kurma zemini (açık veri + mimari)

| Veri seti | Ölçek | Not | Kaynak |
|---|---|---|---|
| **FASDD** | 100.000+ (bir kaynakta 120k) görüntü, 3 alt küme (CV / UAV / RS) | Yer-hava-uzay çapraz alan; YOLOv5x ile **~%80 mAP@0.5** | https://essd.copernicus.org/preprints/essd-2023-73/ · https://www.tandfonline.com/doi/full/10.1080/10095020.2024.2347922 |
| **FIgLib** | ~25.000 etiketli orman dumanı görüntüsü, sabit kamera | SmokeyNet referans veri seti | https://www.researchgate.net/publication/358757533_FIgLib_SmokeyNet_Dataset_and_Deep_Learning_Model_for_Real-Time_Wildland_Fire_Smoke_Detection |
| **SmokeyNet** | Model | **Uzam-zamansal** (spatiotemporal) mimari; FIgLib'de baseline'ları geçiyor, insan performansına yaklaşıyor | aynı kaynak |

En yüksek sinyalli mimari dersi: SmokeyNet'in kazancı tek kareden değil **zaman boyutundan** geliyor; duman tek karede belirsiz, hareket örüntüsünde belirgindir (https://www.researchgate.net/publication/358757533_FIgLib_SmokeyNet_Dataset_and_Deep_Learning_Model_for_Real-Time_Wildland_Fire_Smoke_Detection). FIA/BRE'nin bağımsız ölçümü aynı yöne işaret ediyor: dumanın "smokiness" ölçüsü olarak kare kare **RMSE kontrast değişimi** kullanılabilir bulundu (FIA Fact File 90, s.10) — yani sinyal zamansal kontrast değişiminde. İki bağımsız orijin aynı sonucu gösteriyor. — `doğrulanmış`

---

# BÖLÜM B — İplik / tekstil fabrikasında hata tespiti

## B1. Önce ayrım: "iplik fabrikası"nda hata, altı ayrı aşamada altı ayrı iştir

| Aşama | Aranan hata | Dünya lideri çözüm | Kaynak |
|---|---|---|---|
| Harman-hallaç (blowroom) | Yabancı elyaf, polipropilen, bitkisel madde | **Uster Jossi Vision Shield 2** — PIRT görüntü tanıma; hat başına **yılda 25.000 kg+** hammadde tasarrufu iddiası | https://www.uster.com/products/in-line-process-control/uster-jossi-vision-shield/ · https://www.textileworld.com/textile-world/2016/01/ultimate-fiber-cleaning-with-the-new-uster-jossi-vision-shield-2/ |
| Ring iplik | Ends-down (kopuş), iğ verimi | **Rieter ISM premium** — tüm Rieter ring/kompakt makinelerde **standart**; iğ başına gerçek zamanlı izleme + LED; ROBOspin robotu kopuş konumunu ISM'den alır | https://www.rieter.com/products/systems/ring-spinning-machines/ring-spinning-machine-g-38 |
| Bobin/sarım | İnce yer, kalın yer, nope, yabancı madde, renk sapması | **Uster Quantum 4.0**, **Loepfe YarnMaster PRISMA**, Premier iQ | aşağıda B2 |
| Laboratuvar | Hata sınıflandırma, kıyaslama | **Uster Classimat 5** + Uster Statistics | https://www.uster.com/products/staple-yarn-testing/uster-classimat/ |
| Örme | Delik, iğne izi, yağ lekesi, çizgi | **Smartex CORE** (makine üstü) | https://www.smartex.ai/products |
| Kumaş muayene | Dokuma/örme kumaş hataları | **Uster Fabriq Vision 2**, **Shelton WebSpector** | aşağıda B3 |
| Kıvılcım / yangın | Kanal içi kızgın partikül | **Firefly**, **Arosa 5i** | https://arosasystems.com/spinning-nonwovens-recycling/ |

## B2. Kritik gerçek: iplik hatası pazarı kamerayla değil, sensör füzyonuyla kapalı

Loepfe YarnMaster PRISMA **kızılötesi optik + RGB optik + kapasitif + triboelektrik** sensörleri sinyal füzyonuyla birleştirir; RGB sensörü ipliği tam spektrumda aydınlatarak en küçük ton/parlaklık farkını yakalar, P4 triboelektrik sensörü farklı hammaddelerin yarattığı elektrik yükü farkını ölçerek **beyaz polipropilen kontaminasyonunu** tespit eder (https://www.loepfe.com/components/yarnmaster-r-prisma). — `doğrulanmış` (üretici teknik sayfası + bağımsız sektör basını: https://www.textileworld.com/textile-world/new-products/2019/07/loepfe-presents-brand-new-yarn-clearer-generation-the-yarnmaster-prisma/)

Uster Quantum 4.0 kapasitif ve fotoelektrik sensörleri tek ünitede birleştirir; koyu/açık yabancı elyaf, bitkisel madde ve polipropilen için **ayrı sınıflandırma ve temizleme**, ayrıca Smart Clearing Technology ile ayar yükünü azaltma sunar (https://www.uster.com/products/in-line-process-control/uster-quantum/ · https://www.textileworld.com/textile-world/new-products/2021/03/new-uster-quantum-4-0-yarn-clearer-offers-spinners-the-best-of-both-worlds/). — `doğrulanmış`

Bunun stratejik anlamı sert: bu cihazlar **her sarım kafasında**, hat hızında, kesme aktüatörüne doğrudan bağlı çalışıyor ve iplik bir kameranın çözebileceğinden çok daha ince bir ölçekte (kütle, yük, renk) ölçülüyor. **Kamera tabanlı genel amaçlı bir sistemin bu işi devralması gerçekçi değildir** — Uster/Loepfe/Premier üçlüsünün pazarına dışarıdan girilmez. — `[yorum]`

## B3. Kameranın gerçekten kazandığı üç yer

**(a) Örme makinesi üstü tespit — Smartex.** Dairesel örme makinesine monte optik sensör + ML ile üretim anında hata tespiti; hatalı üretimi **%5'ten sıfıra yakın** seviyeye indirdiği AB fonu başarı hikâyesinde belirtiliyor (https://eic.ec.europa.eu/success-stories/smartex-detection-defective-textile-production_en). Türkiye referansı var: **Ekoten**, Smartex ile hatalı kumaş üretiminde **%80 azalma** bildirmiş (https://apparelimpact.org/solutions/smartex-ai-enabled-real-time-quality-control/). — `ikincil` (iki farklı orijin ama ikisi de Smartex'in kendi anlattığı vakaya dayanıyor olabilir; bağımsız denetim görülmedi)

**(b) Kumaş muayene — Shelton ve Uster.** Shelton WebSpector **%99 tespit doğruluğu** ve WebClassifier ile deseni hatadan ayırma iddiasında (https://sheltonvision.co.uk/); Uster Fabriq Vision 2 AI destekli stil ayarıyla yeni bir artikeli **10 dakikadan kısa sürede** devreye alma iddiasında (https://www.uster.com/products/fabric-inspection/uster-fabriq-vision/ · https://www.textileworld.com/textile-world/2026/03/uster-fabric-vision-2-developed-to-assist-fabric-producers-transition-from-manual-to-automated-inspection-with-the-same-staff/). Sektörel derlemeye göre bu sınıf sistemler **1.000 m/dk hızda 0,1 mm'den küçük** hataları yakalayabiliyor (https://apparelresources.com/technology-news/manufacturing-tech/technology-levels-for-fabric-inspection/). — `ikincil` (hepsi satıcı beyanı veya satıcıya dayanan sektör basını; bağımsız ölçüm yok)

**(c) Ring salonunda görsel izleme — gerçek boşluk.** Rieter ISM premium yalnız **Rieter'in kendi** makinelerinde standart (https://www.rieter.com/products/systems/ring-spinning-machines/ring-spinning-machine-g-38); karışık ve eski makine parkına sahip fabrikalarda iğ bazlı elektronik izleme yok. Kameranın burada yakalayabileceği şeyler — kopuş yoğunluğu, sarma/lapping, uçuntu birikimi, doff durumu, boş/dolu masura, operatör güvenliği — makineye dokunmadan retrofit edilebilir. Bu, AurasVision'ın mevcut yeteneğine (RTSP alımı, GPU pipeline, zone, olay, kanıt karesi) en yakın duran iştir. — `spekülatif` (boşluğun varlığı Rieter'in "kendi makinelerinde standart" beyanından çıkarım; sahada bu boşluğu doldurmayan bir rakip olmadığı DOĞRULANMADI)

## B4. Veri ve model zemini — ve neden generic obje tespiti yetmiyor

Açık veri setleri: **TILDA**, **AITEX**, **DAGM2007**, **Tianchi** ve **ZJU-Leaper**; Tianchi seti 5.913 hatalı + 3.663 temiz görüntü, 20 hata sınıfı, 9.523 anotasyon, 2446×1000 çözünürlük (https://arxiv.org/pdf/2505.07040 · http://www.qaas.zju.edu.cn/zju-leaper/). — `doğrulanmış`

Ama asıl sinyal şu: Tianchi kumaş veri setinde optimize edilmiş modellerin ulaştığı seviye **%65,2 mAP@0.5** (https://arxiv.org/pdf/2505.07040). Aynı literatür derlemesi, standart ve paylaşılabilir veri setine erişimin araştırmacılar için hâlâ bir sorun olduğunu, TILDA/DAGM2007/Tianchi'nin kapsamının sınırlı olduğunu belirtiyor (https://onlinelibrary.wiley.com/doi/10.1111/cote.70044?af=R). — `doğrulanmış`

Yani **hata sınıflarını toplayıp denetimli obje tespiti eğitmek endüstriyel kaliteye ulaşmıyor**. Alternatif yön anomali tespiti: PatchCore, MVTec AD üzerinde görüntü seviyesinde **~%99,1 AUROC** ile, üstelik few-shot rejimde çalışıyor (https://arxiv.org/pdf/2307.10792 · https://www.emergentmind.com/topics/patchcore). Yaklaşım tersine dönüyor — hatayı öğretmek yerine **"normal"i öğretip sapmayı işaretlemek**. Kumaşta bu doğal bir uyum: normal doku periyodiktir, hata periyodikliği bozar. — `doğrulanmış` (iki bağımsız kaynak: hakemli arXiv çalışması + bağımsız derleme)

Güncel araştırma yönü: sürekli öğrenme ve alan-uyarlamalı eşikleme, değişen üretim ortamlarında dağıtım için sağlam yönler olarak işaretleniyor (https://github.com/m-3lab/awesome-industrial-anomaly-detection). — `ikincil`

---

# Karar önerisi

## Yangın tarafı

**Konumlandırma (en kritik karar):** AurasVision'ı "sertifikalı yangın alarm sistemi" olarak konumlandırma. A2'deki bulgu nettir — EN 54'te video karşılığı yok, sertifika BOSEC/CNPP/VdS gibi ulusal-özel yollardan alınıyor ve yıllar sürüyor (Bosch Kasım 2016'da başvurdu, onay Kasım 2017'de geldi). Doğru konumlandırma: **mevcut yangın sistemine paralel erken uyarı + görsel doğrulama + kanıt katmanı**. Bu, projenin zaten sahip olduğu kanıt karesi ve olay altyapısına birebir oturuyor. — `[yorum]` (Bulgu A2 ve A3'ten çıkarım; ölçüm değil). Risk sınıfı: **approval** (can güvenliği iddiası içeren her metin ve arayüz onaydan geçmeli).

**Mimari:** tek kare sınıflandırıcı değil, **iki aşamalı + zamansal** (kare-seviyesi öneri → N-kare zamansal doğrulama), SmokeyNet ve BRE'nin RMSE bulgusuyla uyumlu (Bulgu A5). — `[yorum]` Termal kanal opsiyonel ikinci sensör olarak planlanmalı — FLIR/Fire Rover'ın atık sektöründeki hâkimiyeti bunun kanıtı (A4).

**Kurulum disiplini ürünün parçasıdır:** ISO/TS 7240-30'un getirdiği şart — maskelenen bölgeler, saha performans testi, arka plan/aydınlatma değerlendirmesi — bizde de bir **kurulum sihirbazı + saha kabul testi** olarak kodlanmalı. A3'teki %58 rakamı, bunu yapmayan her kurulumun beklenen sonucudur. — `[yorum]`

## Tekstil tarafı

**Girme:** iplik temizleme (Uster/Loepfe/Premier). B2 gereği kapalı pazar. — `[yorum]`

**Gir:** üç işten oluşan paket, mevcut mimariye yakınlıktan uzağa doğru sıralı (aşağıdaki sıralama bulgulardan çıkarımdır — `[yorum]`):
1. **Ring/salon görsel izleme** (kopuş yoğunluğu, lapping, uçuntu, doff, operatör güvenliği) — retrofit boşluğu (B3c), mevcut zone/olay/kanıt altyapısı doğrudan kullanılabilir, rakip makine üreticisine bağlı. — `spekülatif` (B3c'deki doğrulanmamış boşluk varsayımına dayanıyor)
2. **Yangın/kıvılcım erken uyarı** — Bölüm A ile **aynı motor**; tekstil fabrikası zaten yüksek riskli bir ortam (uçuntu, sürtünme, kanal sistemleri: https://risklogic.com/fire-protection-for-the-textile-industry). Tek geliştirmeyle iki ürün.
3. **Kumaş muayene** — en yüksek değer ama en zorlu rakip seti (Shelton, Uster); ancak PatchCore benzeri anomali yaklaşımı (B4) veri toplama maliyetini düşürdüğü için orta vadede gerçekçi. — `[yorum]`

**Yöntem kararı:** hata sınıfı etiketleyip denetimli tespit eğitmek yerine **normal-öğrenen anomali tespiti** temel al (B4: Tianchi %65,2 mAP vs MVTec %99,1 AUROC). Bu, tek bir fabrikada veri toplayıp devreye alma süresini dramatik biçimde kısaltır. — `[yorum]` (kısalma miktarı ölçülmedi)

---

# Açık sorular

- **ISO 7240-29:2024'ün tam metni görülmedi** (iso.org 403 döndü). 2024 tam standardının 2017 TS'ine göre neyi değiştirdiği — özellikle yanlış alarm testi eklenip eklenmediği — doğrulanmadı. Sonraki adım: TSE veya BSI üzerinden metni edin.
- **Türkiye mevzuatı bakılmadı.** "Binaların Yangından Korunması Hakkında Yönetmelik" ve TS EN 54 uygulamasında video yangın dedektörünün statüsü araştırılmadı. Satış öncesi zorunlu; yanlış konumlandırma yasal risk.
- **Satıcı beyanları bağımsız doğrulanmadı:** Shelton %99, Smartex %5→~0 ve Ekoten %80, Uster 1.000 m/dk & 0,1 mm rakamlarının hiçbirinde üçüncü taraf ölçüm görülmedi. Bunlar hedef değil, **iddia edilen tavan** olarak okunmalı.
- **ALERTCalifornia'nın 915 yangın rakamı** tek orijinli (NPR ağı muhabirliği + Cal Fire beyanı); bağımsız denetim raporu aranmadı.
- **B3c'deki "retrofit boşluğu" doğrulanmadı.** Rieter dışı makine parkı için iğ/kopuş izleme çözümü satan bir rakip olup olmadığı taranmadı (Loepfe, Premier, Savio, Murata, Bräcker portföyleri bakılmadı). Bu, tekstil tarafındaki 1 numaralı öneriyi doğrudan geçersiz kılabilecek tek bulgudur — **sıradaki iş bu olmalı**.
- **Hedef müşteri tanımlı değil.** "İplik fabrikası" ring mi, open-end mi; örme mi dokuma mı besliyor; makine parkı hangi marka? B1'deki altı aşamadan hangisine gireceğimiz bu cevaba bağlı ve şu an varsayımla ilerliyoruz.
- **Fiyat/rekabet ekonomisi bakılmadı.** Fire Rover, Pano AI, Smartex, Shelton'ın fiyat seviyeleri ve Türkiye'de mevcudiyeti araştırılmadı.
- **Repo durumu:** `src/` altında yangın/duman/tekstil ile ilgili hiçbir modül yok — mevcut modüller sayım, plaka, yüz, PTZ, zone, kanıt (`git rev-parse --short HEAD` → `a9bbba5`, `grep -rniE "fire|smoke|duman|yangın|flame|fabric|yarn" src/` → eşleşme yok). Her iki iş de sıfırdan yeni modül demektir.
