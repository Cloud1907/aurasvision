"""Dedektör motoru soyutlaması — lisans kapısı burada.

Neden ayrı bir katman: bu ürün KAPALI KAYNAK ticari olarak satılıyor ve
Ultralytics YOLO **AGPL-3.0**'dır. AGPL, GPL'in "SaaS boşluğunu" kapatan
sürümüdür: modeli bir sunucu arkasında sunmak da dağıtım sayılır ve kaynak
açma yükümlülüğü doğurur. AurasVision tam olarak budur (FastAPI sunucusu +
worker), dolayısıyla motor seçimi bir performans tercihi değil HUKUKİ bir
karardır ve import zincirinde saklı kalmamalıdır.

Kural: **varsayılan motor Apache-2.0'dır.** AGPL motor ancak yapılandırmada
açıkça kabul edilirse yüklenir (`fire.agpl_kabul: true`). Böylece karar
config.yaml'da görünür, denetlenebilir ve geri alınabilir olur.

Motorlar:
  rfdetr       Apache-2.0 · RF-DETR (Roboflow). N/S/M/L detection ağırlıkları
               Apache-2.0'dır; **XL ve 2XL PML 1.0'dır ve buraya girmez.**
               DINOv2 omurga — dumanı buhardan/tozdan ayırmak yerel dokuyla
               değil küresel bağlamla olur; bu iş için doğru önsel.
               Paketin ultralytics bağımlılığı yoktur (doğrulandı 2026-09-02).
  ultralytics  AGPL-3.0 · yalnız geliştirme/karşılaştırma için. Mevcut
               count/plate/face hatları bu motorda; onların taşınması ayrı iş.

Ayrıntı ve aday karşılaştırması: docs/yangin-modeli.md
"""
from __future__ import annotations

from typing import Any

VARSAYILAN_MOTOR = "rfdetr"

# Motor → ağırlıkların ve çalışma-anı paketinin lisansı.
# RF-DETR XL/2XL (PML 1.0) bilinçli olarak YOK: bu tabloya girmeyen motor
# yüklenemez, yani ticari olmayan katman kazayla seçilemez.
LISANSLAR = {
    "rfdetr": "Apache-2.0",
    "ultralytics": "AGPL-3.0",
}

# Açık onay istemeyen, ticari kullanımda serbest lisanslar.
SERBEST = {"Apache-2.0"}


class LisansHatasi(RuntimeError):
    """Motor lisansı ürünün dağıtım modeliyle bağdaşmıyor."""


def lisans_kapisi(motor: str, agpl_kabul: bool = False) -> str:
    """Motorun lisansını döndürür; kapalı kaynak üründe riskliyse reddeder."""
    lisans = LISANSLAR.get(motor)
    if lisans is None:
        raise LisansHatasi(
            f"Bilinmeyen dedektör motoru: '{motor}'. Seçenekler: "
            f"{', '.join(sorted(LISANSLAR))} (`fire.engine`). "
            "RF-DETR XL/2XL bilinçli olarak yoktur — PML 1.0 lisanslıdır."
        )
    if lisans in SERBEST or agpl_kabul:
        return lisans
    raise LisansHatasi(
        f"'{motor}' motoru {lisans} lisanslıdır. AGPL, modeli sunucu arkasında "
        "sunmayı da dağıtım sayar; kapalı kaynak bir üründe kullanmak ya tüm "
        "kaynağı açmayı ya Ultralytics Enterprise lisansını gerektirir. "
        "Bilinçli olarak devam edecekseniz `fire.agpl_kabul: true` yazın; "
        f"ticari olarak temiz seçenek `fire.engine: {VARSAYILAN_MOTOR}` "
        "(Apache-2.0). Ayrıntı: docs/yangin-modeli.md"
    )


def normalize(tespitler: Any, adlar: dict) -> list[tuple]:
    """Arka uç çıktısını `(sinif, x1, y1, x2, y2, conf)` listesine çevirir.

    Hedef biçim `DumanTakip.guncelle`'nin beklediğidir — motor değişse de
    zamansal doğrulama mantığı değişmesin diye tek dönüşüm noktası burası.
    Ad haritasında olmayan sınıf id'si SESSİZCE DÜŞMEZ, ham id'siyle görünür:
    eksik ad bir yapılandırma hatasıdır ve kaybolarak değil görünerek fark edilir.
    """
    if tespitler is None:
        return []
    kutular = getattr(tespitler, "xyxy", None)
    if kutular is None or len(kutular) == 0:
        return []
    guvenler = getattr(tespitler, "confidence", None)
    sinif_idler = getattr(tespitler, "class_id", None)
    cikti = []
    for i, kutu in enumerate(kutular):
        cid = int(sinif_idler[i]) if sinif_idler is not None else 0
        conf = float(guvenler[i]) if guvenler is not None else 0.0
        x1, y1, x2, y2 = (float(v) for v in kutu)
        cikti.append((adlar.get(cid, str(cid)), x1, y1, x2, y2, conf))
    return cikti


class Dedektor:
    """Tek kare tespit arayüzü — motor bağımsız."""

    def __init__(self, motor: str, model: str, adlar: dict, esik: float,
                 _ic: Any) -> None:
        self.motor = motor
        self.model = model
        self.adlar = adlar
        self.esik = float(esik)
        self._ic = _ic

    def tespit(self, bgr) -> list[tuple]:
        """BGR kareden `(sinif, x1, y1, x2, y2, conf)` listesi üretir."""
        if self.motor == "rfdetr":
            return normalize(self._rfdetr_tahmin(bgr), self.adlar)
        return normalize(self._ultralytics_tahmin(bgr), self.adlar)

    def tespit_coklu(self, bgrler: list) -> list[list[tuple]]:
        """Birden çok kareyi (ör. 2×2 karolar) tek çağrıda geçirir; sıra korunur."""
        if not bgrler:
            return []
        if self.motor == "rfdetr":
            cikti = self._ic.predict([self._rgb_tensor(b) for b in bgrler],
                                     threshold=self.esik)
            if not isinstance(cikti, list):
                cikti = [cikti]
            return [normalize(c, self.adlar) for c in cikti]
        return [self.tespit(b) for b in bgrler]

    def _rgb_tensor(self, bgr):
        """BGR numpy → modelin AYGITINDA (C,H,W) float [0,1] RGB tensörü.

        rfdetr'e numpy/PIL verilince to_tensor + yeniden boyutlama + normalize
        CPU'da koşar: 2K karede 2×2 karo tek başına ~2,6 çekirdek yiyordu
        (ölçüm 2026-09-07, torch 4 iş parçacığı). Ham baytlar GPU'ya taşınıp
        dönüşüm orada yapılınca CPU payı düşer; H2D kopyası karo başına ~3,5 MB.
        """
        import numpy as np
        import torch

        dev = getattr(getattr(self._ic, "model", None), "device", None)
        if dev is None:
            dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        t = torch.from_numpy(np.ascontiguousarray(bgr)).to(dev)
        return t.permute(2, 0, 1).flip(0).float().div_(255.0)   # BGR→RGB, [0,1]

    def _rfdetr_tahmin(self, bgr):
        return self._ic.predict(self._rgb_tensor(bgr), threshold=self.esik)

    def _ultralytics_tahmin(self, bgr):
        r = self._ic.predict(bgr, conf=self.esik, verbose=False)[0]
        if r.boxes is None or not len(r.boxes):
            return None
        return _UltralyticsGorunumu(r)


class _UltralyticsGorunumu:
    """Ultralytics `Results`'ı supervision.Detections yüzeyine uyarlar."""

    def __init__(self, r) -> None:
        self.xyxy = r.boxes.xyxy.tolist()
        self.confidence = r.boxes.conf.tolist()
        self.class_id = r.boxes.cls.int().tolist()


def yukle(motor: str, model: str, adlar: dict, esik: float = 0.35,
          agpl_kabul: bool = False, device_pref: str = "auto") -> Dedektor:
    """Motoru lisans kapısından geçirip yükler."""
    lisans_kapisi(motor, agpl_kabul)
    if motor == "rfdetr":
        return Dedektor(motor, model, adlar, esik, _rfdetr_yukle(model))
    from .detect import load_yolo
    return Dedektor(motor, model, adlar, esik, load_yolo(model, device_pref))


def _rfdetr_yukle(model: str):
    """RF-DETR ağırlığını yükler. Paket yoksa NE YAPILACAĞINI söyler."""
    try:
        from rfdetr import RFDETRSmall
    except ImportError as e:
        # Paket gerçekten yoksa e.name == "rfdetr"; aksi hâlde bağımlılığı ya da
        # başka iş parçacığının yarım kalmış import'u patlamıştır (2026-09-09:
        # worker açılışında SigLIP/timm yüklenirken "kurulu değil" sanıldı).
        # Asıl hata mesajda GÖRÜNSÜN, yoksa yanlış teşhis konur.
        if getattr(e, "name", None) == "rfdetr":
            raise ImportError(
                "rfdetr paketi kurulu değil (Apache-2.0, ticari serbest). "
                "Kurulum: pip install rfdetr — ayrıntı docs/yangin-modeli.md"
            ) from e
        raise ImportError(f"rfdetr import edilemedi (paket var, bağımlılık/yarış): {e}") from e
    return RFDETRSmall(pretrain_weights=model)
