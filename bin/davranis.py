#!/usr/bin/env python3
"""Her turda enjekte edilen davranış sözleşmesi metinleri.

Router'ın SEÇİM mantığından ayrıdır: burada "kim seçildi" değil, "seçilen
nasıl davranmalı" yaşar. Ayrım route.py'yi 400 satır sınırının altında tutar
ve metinleri tek yerde toplar (kalite ratchet'i, ADR-0004).

TASARIM KURALI (2026-08-15): buradaki metin TALİMAT taşır, GEREKÇE taşımaz.
Enjeksiyon her prompt'a girer, yani maliyeti tur sayısıyla çarpılır; bir
kuralın NEDEN var olduğu oturum başına bir kez yüklenen AGENTS.md'de
("Davranış sözleşmesi" bölümü) ya da skill dosyasında durur. Tavan bekçisi:
tests/test_baglam_butcesi.py — tavanı yükseltmek bilinçli karardır.
"""

# Karşılama katmanı. Derinlik aurasprime/SKILL.md'de; burada yalnız DAVRANIŞ.
KARSILAMA = (
    "🎩 AurasPrime karşılaması — YENİ iş isteğinde üç satırla başla; mikro "
    "işte ve aynı işin takip turunda atla (yeni konu takip turu değildir):\n"
    "📋 Anladığım: <tek cümle, kullanıcının diliyle>\n"
    "📌 Geçmiş: <kayıttan tarih + karar | 'kayıt yok'>\n"
    "➡️ Veriyorum: <skill> — <ne · çıktı · neye dokunmayacak>\n"
    "Üç satır yeter; soru yağmuru açma, belirsizlikte varsayımı yaz.")

# Hafıza katmanı: kaydı router okur, ajan yalnız yazar.
GECMIS_VAR = ("📌 Geçmiş (KAYITTAN; kendi belleğinden yazma, ilgisizse "
              "'kayıt yok' de):\n{kayitlar}")

GECMIS_YOK = "📌 Geçmiş: bu aramada kayıt çıkmadı → 'kayıt yok' yaz; uydurma."


def gecmis_blogu(kayitlar):
    """Karşılamaya enjekte edilecek hafıza satırı ([(tarih, satır)])."""
    if not kayitlar:
        return GECMIS_YOK
    return GECMIS_VAR.format(
        kayitlar="\n".join(f"  {tarih}  {satir}" for tarih, satir in kayitlar))


# Analiz katmanı: işin sahibi hangi disiplin? Tek sahip — zincir değil.
SAHIP_VAR = ("👤 Sahip disiplin: {owner} — o alanın uzmanı gibi çalış; "
             "sahiplik tektir.")

SAHIP_YOK = "👤 Sahip disiplin: BELİRSİZ — ilk cümlede belirle ya da sor."

# İtiraz yükümlülüğü: yalnız yazma riskli turlarda ödenir (bkz. sozlesme).
ITIRAZ = ("İTİRAZ YÜKÜMLÜLÜĞÜ: istek yanlış/eksik/riskliyse UYGULAMADAN ÖNCE "
          "tek paragraf itiraz yaz (ne · neden · alternatif); ısrar gelirse "
          "uygula ve belirt.")

# Görünürlük sözleşmesi: kullanıcı ne olduğunu yazışmadan anlamalı.
BASLIK = ("Başlık (sohbet turunda da):\n"
          "🧭 Skill: <yüklediğin | 'yok — gerekçe'>  ·  Sınıf: {task_class}"
          "  ·  Risk: {risk}\n"
          "👤 Sahip: {owner}\n"
          "🔧 Yaptım: <tek cümle, somut — dosya/komut/sonuç>\n"
          "Alt-ajan varsa: 🤖 Ajan: <rol> — <ne için>")


def sozlesme(owner, task_class, risk):
    """Sahip · (riskliyse) itiraz · başlık satırları.

    İtiraz yalnız `auto` DIŞI turlarda enjekte edilir: itiraz edilecek bir
    mutasyon yokken her sohbet turuna 240 karakter eklemek, kuralı
    güçlendirmez yalnız bağlamı pahalılaştırır. Tam kural AGENTS.md'dedir
    (oturum başına bir kez yüklenir). Bekçi: tests/test_baglam_butcesi.py
    """
    satirlar = [SAHIP_VAR.format(owner=owner) if owner else SAHIP_YOK]
    if risk != "auto":
        satirlar.append(ITIRAZ)
    satirlar.append(BASLIK.format(task_class=task_class, risk=risk,
                                  owner=owner or "belirsiz"))
    return satirlar
