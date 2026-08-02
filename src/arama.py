"""Görünüm araması — arşivde serbest metinle nesne bulma (SigLIP).

Worker izlediği nesnelerden örneklenmiş kırpmaları vektöre çevirir (768d),
olay yoluyla veritabanına yazılır. Arama: metin → vektör → kosinüs benzerliği
→ en yakın kırpmalar → kayıtta o ana atlama.

Model seçimi BİLİNÇLİ: SigLIP (Apache-2.0) ticari üründe kullanılabilir;
NVIDIA LocateAnything-3B teknik olarak cazip ama lisansı ticari kullanımı
YASAKLIYOR — ürüne giremez (kullanıcıya açıklandı, 2026-08-02). Ayrıca 3B'lik
VLM sürekli çok-kamera analizi için yanlış ölçek; SigLIP kırpma başına
milisaniye harcar.

KVKK: kırpmalar kişi görüntüsü içerir — arama.keep_days sonunda küçük
görüntüler silinir (vektör kalır: geriye kişi çıkarılamaz, arama "şu tarihte
şuradaydı" cevabını korur ama görüntü kanıtı süreli).
"""
from __future__ import annotations

import functools
import time
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

BOYUT = 768   # ViT-B-16-SigLIP çıktısı — şema bu boyuta göre kurulur


@functools.lru_cache(maxsize=1)
def _model():
    import open_clip
    import torch
    ad, agirlik = "ViT-B-16-SigLIP", "webli"
    model, _, on_isleme = open_clip.create_model_and_transforms(ad, pretrained=agirlik)
    tok = open_clip.get_tokenizer(ad)
    aygit = "cuda" if torch.cuda.is_available() else "cpu"
    return model.eval().to(aygit), on_isleme, tok, aygit


def goruntu_vektorleri(bgr_kirpmalar: list) -> list:
    """BGR kırpma listesi → L2-normalize float32 vektör listesi."""
    import cv2
    import torch
    from PIL import Image
    model, on_isleme, _, aygit = _model()
    girdiler = torch.stack([
        on_isleme(Image.fromarray(cv2.cvtColor(k, cv2.COLOR_BGR2RGB)))
        for k in bgr_kirpmalar]).to(aygit)
    with torch.no_grad():
        v = model.encode_image(girdiler)
        v = v / v.norm(dim=-1, keepdim=True)
    return [x.astype("float32") for x in v.cpu().numpy()]


def metin_vektoru(sorgu: str):
    import torch
    model, _, tok, aygit = _model()
    with torch.no_grad():
        v = model.encode_text(tok([sorgu]).to(aygit))
        v = v / v.norm(dim=-1, keepdim=True)
    return v.cpu().numpy()[0].astype("float32")


def kucuk_kaydet(cfg, bgr_kirpma) -> str:
    """Sonuç listesinde gösterilecek küçük görüntü; output'a göre göreli yol döner."""
    import cv2
    kok = _ROOT / cfg.get("paths.output_dir", "output") / "arama" / time.strftime("%Y-%m-%d")
    kok.mkdir(parents=True, exist_ok=True)
    h, w = bgr_kirpma.shape[:2]
    if w > 240:
        bgr_kirpma = cv2.resize(bgr_kirpma, (240, max(1, int(h * 240 / w))))
    ad = f"{uuid.uuid4().hex[:12]}.jpg"
    cv2.imwrite(str(kok / ad), bgr_kirpma, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return f"arama/{time.strftime('%Y-%m-%d')}/{ad}"


def temizle(cfg) -> int:
    """Süresi dolan küçük görüntüleri siler (klasör adı = tarih). Vektörler kalır."""
    import shutil
    from datetime import date, timedelta
    gun = int(cfg.get("arama.keep_days", 30))
    if gun <= 0:
        return 0
    kok = _ROOT / cfg.get("paths.output_dir", "output") / "arama"
    if not kok.is_dir():
        return 0
    sinir = (date.today() - timedelta(days=gun)).isoformat()
    n = 0
    for k in kok.iterdir():
        if k.is_dir() and k.name < sinir:
            shutil.rmtree(k, ignore_errors=True)
            n += 1
    return n
