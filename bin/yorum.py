#!/usr/bin/env python3
"""PR yorumunun GÖVDESİ — inceleme kararının insana görünen yüzü.

Neden `incele.py`'den ayrı: orası KARAR verir (hangi risk, hangi bulgu, merge
mi insan mı), burası o kararı ANLATIR. İkisi ayrı sebeple değişir — bu oturumda
gövde biçimi dört kez değişti (tanı bloğu, enjeksiyon uyarısı, tur/kapsam
satırı, marker'ın koşullu SHA'sı) ve hiçbirinde karar tablosuna dokunulmadı.
Aynı dosyada durdukları sürece her biçim değişikliği, karar mantığının diff'ini
kirletiyordu.

Ayrılma anı ölçülüdür: `incele.py` kırpma düzeltmesiyle 407 satıra çıkıp
ratchet'i deldi (taban 400). Tabanı yükseltmek borcu meşrulaştırırdı; doğru
karşılık zaten kayıtlı olan yapısal notu uygulamaktı.

Tasarım kuralı: buradaki hiçbir fonksiyon dış dünyaya dokunmaz ve karar
üretmez. Girdi kararın kendisidir, çıktı dizedir — bu yüzden testi ucuzdur.
"""
from tur import TUR_TAVANI, marker_uret

SIMGE = {"merge": "✅", "insan": "👤", "engel": "⛔"}


def ozet_govde(risk, bulgular, sonuc, k, gerekce, ci_ozet,
               enjeksiyon=False, tani="", tur=1, head_sha="",
               p0gecmis=False, artimli=False, yeniden=False,
               incelendi=True):
    """PR yorumu — duvar değil, KARAR biçiminde. Okunmayan yorum yoktur."""
    kapsam = "son turdan beri" if artimli else "tüm diff"
    satir = [f"## {SIMGE[k]} Bağımsız inceleme — {k.upper()}",
             "",
             f"**Karar:** {gerekce}",
             f"**Risk sınıfı:** `{risk}` · **CI:** {ci_ozet} · "
             f"**Codex:** {sonuc or '—'}",
             f"**Tur:** {tur}/{TUR_TAVANI} · **Kapsam:** {kapsam}"
             + (" · biçim hatası sonrası yeniden soruldu" if yeniden else ""),
             ""]
    if tani:
        satir += ["<details><summary>Ayrıştırılamayan çıktının sonu</summary>",
                  "", "```", tani, "```", "</details>", ""]
    if enjeksiyon:
        satir += ["> ⚠️ Diff, inceleyiciye talimat veriyor olabilir "
                  "(enjeksiyon şüphesi). Hüküm otomatik merge için yeterli "
                  "sayılmadı.", ""]
    for sev in ("P0", "P1", "P2"):
        for b in bulgular[sev]:
            satir.append(f"- `{sev}` {b}")
    if not any(bulgular.values()):
        satir.append("Bulgu yok.")
    satir += ["", "---",
              "Çapraz-vendor risk sinyali (Codex), makine kanıtı değil. "
              "Merge koşulu: CI yeşil **ve** P0 yok. P1 bloklamaz, kararı "
              "insana taşır.",
              # SHA yalnız GERÇEKTEN incelendiyse yazılır (bkz. marker_uret).
              marker_uret(tur, head_sha if incelendi else "", p0gecmis)]
    return "\n".join(satir)
