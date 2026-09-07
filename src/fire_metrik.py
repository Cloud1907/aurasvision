"""Model metriği → ÜRÜN metriği köprüsü (çalışma anında kullanılmaz).

`src/fire.py` çalışma-anı modülüdür; burası ANALİZ: "bu model bu yapılandırmada
yeterli mi" sorusunu sayıya çevirir. Ayrı durmasının sebebi yalnız dosya boyutu
değil — çalışma anında hiçbir kare bu fonksiyonlardan geçmez, model seçerken
ve eşik ayarlarken geçer.

Neden gerekli: `mAP` bu üründe başarı ölçütü DEĞİLDİR. DumanTakip pencere
içinde N kare onay arıyor, dolayısıyla süren bir olayı yakalamak için
kare-başına recall'ın yüksek olması gerekmez; yanlış alarmı ise kare-başına
yanlış pozitif belirler. Bu ilişki sezgiyle kestirilemez — hesaplanır.
Hesap yanlışsa yanlış güven eşiği seçilir ve hata sahada, alarm gelmediğinde
görülür.

Ölçülmüş sonuç (varsayılan config: 25 fps, vid_stride 3, 6 sn, 4 kare):
pencereye 50 işlenmiş kare sığar, %95 onay için kare-başına recall ≥ %15.
Ayrıntı ve kabul ölçütü: docs/yangin-modeli.md
"""
from __future__ import annotations

from math import comb


def pencere_kare(fps: float, vid_stride: int, pencere_sn: float) -> int:
    """Doğrulama penceresine kaç İŞLENMİŞ kare sığar (kaynak fps'i değil)."""
    efektif = max(1.0, float(fps)) / max(1, int(vid_stride))
    return max(1, int(efektif * float(pencere_sn)))


def onay_olasiligi(kare_recall: float, kare: int, dogrulama: int) -> float:
    """P(en az `dogrulama` kare onaylar | `kare` bağımsız kare, kare-başına recall).

    Model metriğini ÜRÜN metriğine çeviren fonksiyon. Kareler bağımsız
    varsayılır; gerçekte ardışık kareler ilintilidir (aynı poz, aynı ışık),
    yani bu HAFİF İYİMSER bir üst sınırdır — eşik seçerken marj bırak.
    """
    p = min(1.0, max(0.0, float(kare_recall)))
    n, k = int(kare), int(dogrulama)
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    # P(X >= k) = 1 - P(X <= k-1); küçük k için doğrudan toplam yeterli
    kuyruk = sum(comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i)) for i in range(k))
    return max(0.0, min(1.0, 1.0 - kuyruk))


def gereken_recall(kare: int, dogrulama: int, hedef: float = 0.95,
                   adim: float = 0.01) -> float:
    """Hedef onay olasılığı için gereken asgari kare-başına recall.

    Bu sayı `fire.conf` eşiğini yükseltme kararının dayanağıdır: gereken recall
    düşükse (tipik olarak %15'in altı) güven eşiğini yükseltip precision satın
    almak ürünü İYİLEŞTİRİR — mAP düşse bile. `adim` çözünürlüğüdür.
    """
    if int(dogrulama) > int(kare):
        return 1.0        # olanaksız: yanıltıcı düşük sayı dönmesin
    p = 0.0
    while p <= 1.0:
        if onay_olasiligi(p, kare, dogrulama) >= hedef:
            return round(p, 4)
        p += adim
    return 1.0
