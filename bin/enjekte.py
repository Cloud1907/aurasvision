#!/usr/bin/env python3
"""Router enjeksiyonunun METNİ — karar ayrı, anlatım ayrı.

Neden `route.py`'den ayrı: orası KARAR verir (hangi sınıf, hangi skill, hangi
risk), burası o kararı turun başına yazılacak metne çevirir. İkisi ayrı sebeple
değişir — enjeksiyon metni bu sistemde defalarca yeniden yazıldı (karşılama
bloğu, izin sınırı uyarısı, kurulu-değil uyarısı, davranış sözleşmesi,
2026-08-15'te %45 küçültme) ve hiçbirinde karar tablosuna dokunulmadı.

Ayrılma anı ölçülüdür: `niyet.py`'ye ikinci salt-okunur sınıf eklenirken
`route.py` 399'dan 406 satıra çıkıp ratchet'i deldi. Taban yükseltmek borcu
meşrulaştırırdı; bu dosya zaten aylardır pusulada "sıradaki duvar" olarak
görünüyordu (bin/marj.py).

Burada hiçbir fonksiyon karar vermez ve dış dünyaya yazmaz: girdi `route()`
sonucu, çıktı dizedir.
"""
import os

import davranis
import hatirla
from skill_kayit import (profil_disinda, sinifta_izinli, skill_installed,
                         skill_izinli)


def _profil_disi(skill, task_class, pdir):
    """Skill bu sınıfta izinsiz mi (yönetiliyorsa ve sınıfta yoksa)?

    "Yönetilen" iki kanaldan sorulur (inceleme 7. tur): bir profilde
    geçiyorsa `skill_izinli`, projenin profilinden bilinçle ÇIKARILMIŞSA
    `profil_disinda` doğru döner. İkisi de False ise ad gerçekten kapsam
    dışıdır (eklenti skill'i) ve karışılmaz.
    """
    if not skill or sinifta_izinli(skill, task_class, pdir):
        return False
    return skill_izinli(skill, pdir) or profil_disinda(skill, pdir)


def govde(prompt, cfg, pdir, table_is_local, sonuc, sahip_fn):
    """Router enjeksiyonunun METNİ — karar verilmiş, yalnız anlatılıyor."""
    task_class, primary, extras, hits, explicit = sonuc
    profile = os.path.join(".agents", "capability-profiles", f"{task_class}.yml")
    lines = ["[AurasAgents router]"]

    # Karşılama katmanı: açık /komut yoksa işi önce AurasPrime karşılar.
    # Derinlik skill dosyasındadır; burada yalnız DAVRANIŞ enjekte edilir —
    # her turda skill yüklemek maliyet, karşılama kararını skill'in kendi
    # negatif tetikleri verir (küçük iş ve takip turunda tören yapılmaz).
    # Hafıza satırı ajanın takdirinde değildir: kaydı router okur, ajan yazar
    # (2026-08-15 — "hatirla.py ile bak" talimatı her turda atlanıyordu).
    if not explicit:
        lines.append(davranis.KARSILAMA)
        lines.append(davranis.gecmis_blogu(
            hatirla.karsilama_kayitlari(prompt, hits)))

    # Ölçü, zorunlu skill'i düşüren ölçünün AYNISI olmalıdır (inceleme
    # 12. tur): burada "herhangi bir profilde var mı" sorulurken _sinirli
    # turun SINIFINA bakıyordu — bu turda izinsiz bir skill dayatmadan
    # düşürülüp öneride elenirken, kullanıcıya "onu yükle" deniyordu.
    if explicit and _profil_disi(explicit, task_class, pdir):
        lines.append(
            f"/{explicit} bu turun izin sınırı dışında ({task_class} "
            "profilinde yok) — YÜKLEME. Gerekiyorsa kullanıcıya söyle: "
            "profile eklemek bilinçli bir karardır, reviewed PR ister.")
    elif explicit:
        lines.append(f"Kullanıcı açıkça /{explicit} istedi — onu yükle.")

    lines.append(f"Görev sınıfı: {task_class}  |  profil: {profile}")

    if primary:
        lines.append(
            f"ZORUNLU skill: {primary['skill']} "
            f"(ön risk: {primary.get('risk', 'auto')}; "
            f"eşleşen tetik: {', '.join(hits[:4])})")
    else:
        lines.append("Eşleşen skill yok.")
        msg = cfg.get("fallback", {}).get("message")
        if msg:
            lines.append(msg.strip())

    if extras:
        lines.append(f"Ek skill: {', '.join(extras)}")

    if not table_is_local:
        lines.append(
            "Not: bu proje kendi routing.yml'ini taşımıyor, kanonik AurasAgents "
            "tablosu kullanıldı.")
    eksik = [s for s in ([primary["skill"]] if primary else []) + extras
             if not skill_installed(s, pdir)]
    if eksik:
        lines.append(
            f"Uyarı: {', '.join(eksik)} bu projede kurulu değil — /auras ile "
            "bağla, ya da kurulu olmadığını kullanıcıya söyleyip skill'siz çalış.")

    lines.append(
        "Kural: yönlendirilen skill'i YÜKLEMEDEN başlama; yanlışsa tek "
        "cümleyle gerekçelendir — sessizce atlama.")

    lines += _davranis_satirlari(prompt, cfg, primary, task_class,
                                sahip_fn)

    context = "\n".join(lines)
    picked = primary["skill"] if primary else "—"
    if explicit:
        picked = f"/{explicit}"
    summary = f"router → {task_class} · {picked}"
    if extras:
        summary += f" (+{len(extras)})"
    return context, summary


def _davranis_satirlari(prompt, cfg, primary, task_class, sahip_fn):
    """Her turda enjekte edilen davranış sözleşmesi (metinler: davranis.py)."""
    # Risk kuraldan; kural yoksa SINIFTAN türer. Primary'siz incident'a
    # 'auto' yazmak yanlış güven verirdi (inceleme bulgusu, 2026-08-12):
    # research dışı her sınıf temkinli tarafta approval'dır.
    risk = ((primary or {}).get("risk")
            or ("auto" if task_class == "research" else "approval"))
    return davranis.sozlesme(sahip_fn(prompt, cfg, primary), task_class,
                             risk)
