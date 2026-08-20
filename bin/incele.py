#!/usr/bin/env python3
"""incele — merge'ün tek yolu: bağımsız inceleme + risk sınıfına göre karar.

2026-08-07 ölçümü: `bin/codex-review.sh` kurulu ve `codex` CLI çalışır
durumdaydı ama HİÇBİR yerden çağrılmıyordu — açılan 3 PR'da 0 inceleme
yorumu. Kullanıcı da PR'ları okumadığını söyledi. Sonuç: "insan merge"
satırı en güçlü duran ama fiilen boş çalışan halkaydı — ne insan ne makine
incelemesi vardı. Bu araç o boşluğu kapatır.

Neden Codex: farklı SATICI, farklı kör nokta. Bağımsızlık modelin farklı
olmasından gelir, sayısından değil. İnceleme yine de RİSK SİNYALİDİR, makine
kanıtı değildir (AGENTS.md) — bu yüzden CI yeşili ayrıca aranır.

Karar tablosu (sıra önemlidir; politika ve ölçüm en üstte):
  risk = deny · CI kırmızı          → ENGEL
  araç KOŞAMADI (kota/kimlik/ağ)    → İNSAN — "ölçülemedi" ≠ "temiz"
  dalda yeni commit yok             → İNSAN
  okunamadı / tutarsız · P0         → ENGEL (fail-closed) · tur > tavan → İNSAN
  P1 · enjeksiyon şüphesi           → İNSAN (bloklamaz, görünür kalır)
  risk = auto + temiz + CI yeşil    → MERGE ·  diğer → İNSAN

2026-08-12 ölçümü — kapı doğru çalışıyordu ama ÇIKIŞI yoktu: 9 PR'da 62 tur,
~17 saat, 62 hükmün yalnız 2'si temiz. Dört çıkış: P1 bloklamaz · tur tavanı ·
biçim hatasında tek yeniden deneme · artımlı diff (bkz. bin/tur.py).

Kullanım:
  python3 bin/incele.py 13              # incele, PR'a yorum düş, karar bas
  python3 bin/incele.py 13 --merge      # karar MERGE ise birleştir
  python3 bin/incele.py 13 --kuru       # yorum atma (deneme)
  python3 bin/incele.py 13 --json
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import surec  # noqa: E402
from surec import INCELEME_BUTCESI, zaman_asimi_notu  # noqa: E402,F401
from hukum import (ARAC_YOK, BULGU, SONUC,  # noqa: E402,F401
                   arac_kosamadi, bulgulari_ayikla, tutarli_mi)
from tur import (TUR_TAVANI, artimli_base, degismedi_mi,  # noqa: E402,F401
                 marker_oku, marker_uret)
from risk import (APPROVAL, AUTO, DENY, ENJEKSIYON,  # noqa: E402,F401
                  birlestir, enjeksiyon_var_mi, risk_sinifi, yikici_aksiyon)
from contract import (birlesik_risk, on_risk_oku,  # noqa: E402,F401
                      pr_contract)
from yorum import ozet_govde  # noqa: E402,F401


# CI "yeşil" sayılması için KANIT üreten check'in varlığı şart. Önceden
# alakasız bir yeşil check (vercel/render) yeterliydi; evidence workflow'u
# hiç oluşmasa bile kapı geçiyordu.
ZORUNLU_CHECK = re.compile(r"kernel|evidence|gate", re.I)


def _check_kayitlari(satirlar):
    """gh pr checks satırlarını (ad, durum) çiftlerine çevirir."""
    kayit = []
    for s in satirlar:
        if not s.strip():
            continue
        parca = s.split("\t")
        kayit.append((parca[0].strip(),
                      parca[1].strip() if len(parca) > 1 else "?"))
    return kayit


def ci_karari(satirlar):
    """(yesil, ozet) — gh pr checks çıktı satırlarından."""
    kayit = _check_kayitlari(satirlar)
    if not kayit:
        return False, "hiç check yok"
    kanit = [d for a, d in kayit if ZORUNLU_CHECK.search(a)]
    gecen = sum(1 for _a, d in kayit if d == "pass")
    ozet = f"{gecen}/{len(kayit)} pass"
    if not kanit:
        return False, (f"{len(kayit)} check var ama kanıt check'i "
                       "(kernel/evidence/gate) yok")
    if not all(d == "pass" for d in kanit):
        return False, f"kanıt check'i geçmedi ({ozet})"
    return gecen == len(kayit), ozet


def merge_komutu(pr, head_sha):
    """P0 · Merge İNCELENEN commit'e sabitlenir.

    İnceleme bittikten sonra dala yeni commit itilirse --match-head-commit
    olmadan `gh pr merge` incelenmemiş kodu birleştirirdi.
    """
    if not head_sha:
        raise ValueError("head SHA yok — merge incelenen commit'e sabitlenemez")
    return ["gh", "pr", "merge", str(pr), "--merge",
            "--match-head-commit", head_sha]


def _hukum_engeli(bulgular, okunabildi, tutarli):
    """İnceleyicinin hükmünden doğan ENGEL gerekçesi (yoksa boş dize).

    Ayrı tutulur çünkü tavan YALNIZ bunu eskale eder: `deny` ve kırmızı CI
    hüküm değil, politika ve ölçümdür — tavan onları gevşetemez.
    """
    if not okunabildi:
        return ("inceleme çıktısı ayrıştırılamadı — 'okunamadı' 'temiz' "
                "demek değildir")
    if not tutarli:
        return "inceleme hükmü bulgularla tutarsız — hüküm güvenilmez"
    if bulgular["P0"]:
        return f"{len(bulgular['P0'])} adet P0 (merge engelleyici)"
    return ""


def karar(risk, bulgular, ci_yesil, okunabildi, tutarli=True,
          enjeksiyon=False, tur=1, degismedi=False, hata=""):
    """(karar, gerekçe) — merge | insan | engel."""
    if risk == "deny":
        return "engel", "deny sınıfı — break-glass gerekir, kararı agent veremez"
    if not ci_yesil:
        return "engel", "CI yeşil değil"
    if arac_kosamadi(hata):
        # Araç KOŞAMADI: ölçüm yok, hüküm de yok. ENGEL yanlış etiket olurdu
        # (kirli sanılır); MERGE ise kanıtsız geçiş olurdu. Doğru yer İNSAN.
        # Politika ve ölçüm (deny, kırmızı CI) YUKARIDA kaldı — araç yokluğu
        # onları gevşetemez.
        # Sınıfı burada TEKRAR yazmıyoruz: `hata` zaten "araç koşamadı
        # (usage limit)" gibi ÖZGÜL işareti taşıyor. Genel etiketi öne
        # koymak, teşhisin tek işe yarar parçasını gölgeliyordu.
        return "insan", (f"bağımsız inceleme ÖLÇÜLEMEDİ: {hata.strip()[:120]}"
                         " — 'ölçülemedi' 'temiz' demek değildir; karar "
                         "kullanıcının")
    if degismedi:
        # Artımlı modda boş diff "TEMİZ" görünür ve önceki turun bulgusunu
        # silerdi — bu yol otomatik merge'e ASLA açılmaz.
        return "insan", ("dalda yeni commit yok — önceki inceleme geçerli, "
                         "karar kullanıcının")
    engel = _hukum_engeli(bulgular, okunabildi, tutarli)
    if engel:
        if tur > TUR_TAVANI:
            return "insan", (f"{tur}. tur — {engel} · döngü tavana takıldı "
                             f"({TUR_TAVANI} tur), karar kullanıcının")
        return "engel", engel
    if bulgular["P1"]:
        # P1 artık BLOKLAMAZ. Bloklamak, düzeltmeyi bir sonraki turun inceleme
        # yüzeyine çeviriyor ve döngüyü besliyordu (41/62). Bulgu yorumda
        # görünür kalır; "bloklamamak" ile "görmezden gelmek" aynı şey değil.
        return "insan", (f"{len(bulgular['P1'])} adet P1 — bloklamaz, "
                         "merge kararı kullanıcının")
    if enjeksiyon:
        # Güvenlik gereği: enjekte edilmiş diff OTOMATİK merge ettiremesin.
        # ENGEL değil İNSAN — aracın kendi format dizesini içeren meşru
        # PR'lar da eşleşir; ENGEL kalıcı öz-blok üretirdi.
        return "insan", ("diff inceleyiciye talimat veriyor olabilir "
                         "(enjeksiyon şüphesi) — hüküm otomatik merge için "
                         "yeterli sayılmaz")
    if risk == "auto":
        return "merge", "auto risk · inceleme temiz · CI yeşil"
    return "insan", f"{risk} sınıfı — karar kullanıcının"


# --- Dış dünya -------------------------------------------------------------
_kos = surec.kos


def pr_dosyalari(pr):
    kod, out, _e = _kos("gh", "pr", "view", str(pr), "--json", "files",
                        "-q", ".files[].path")
    return [s for s in out.splitlines() if s.strip()] if kod == 0 else []


def pr_head_sha(pr):
    kod, out, _e = _kos("gh", "pr", "view", str(pr), "--json", "headRefOid",
                        "-q", ".headRefOid")
    return out.strip() if kod == 0 else ""


def pr_diff(pr):
    kod, out, _e = _kos("gh", "pr", "diff", str(pr))
    return out if kod == 0 else ""


def pr_yorumlari(pr):
    """PR yorum gövdeleri. Okunamazsa boş liste — sayaç sıfırlanır."""
    kod, out, _e = _kos("gh", "pr", "view", str(pr), "--json", "comments")
    if kod != 0:
        return []
    try:
        return [c.get("body", "") for c in json.loads(out).get("comments", [])]
    except (ValueError, AttributeError, TypeError):
        return []


def ci_durumu(pr):
    """(yesil, ozet) — hiçbir check yoksa yeşil SAYILMAZ."""
    kod, out, _e = _kos("gh", "pr", "checks", str(pr))
    satirlar = [s for s in out.splitlines() if s.strip()]
    if kod != 0 and not satirlar:
        return False, "check okunamadı"
    return ci_karari(satirlar)


def codex_incele(pr, butce=None, base=""):
    """(ham_cikti, hata_notu) — hata notu boşsa çağrı sorunsuz.

    Neden ayrı dönüyor: kapı "ayrıştıramadım" dediğinde SEBEBİ görünmeli —
    teşhis edilemeyen kırmızı, kapalı kapıdan farksızdır.

    `base` verilirse inceleme ARTIMLIDIR: yalnız o SHA'dan beri gelen
    değişikliğe bakılır.
    """
    butce = INCELEME_BUTCESI if butce is None else butce
    komut = ["bash", os.path.join(HERE, "codex-review.sh"), str(pr),
             "--dry-run"]
    if base:
        komut.append(f"--base={base}")
    kod, out, err = _kos(*komut, timeout=butce)
    if kod != 0:
        # Sınıflandırma KIRPMADAN ÖNCE yapılır. Canlı ölçüm 2026-08-16: kota
        # mesajı ("usage limit") çıktının SONUNDAydı, `[:200]` onu kesiyordu
        # ve `arac_kosamadi` göremiyordu — birim test temiz mesajla geçmiş,
        # entegrasyon kırpılmış gerçekle düşmüştü. Sinyali kaybeden kırpma,
        # kırpmadan önce sınıflandırmayı zorunlu kılar.
        hata = f"codex-review.sh exit {kod}: {(err or '').strip()[:200]}"
        m = ARAC_YOK.search(f"{err or ''}\n{out or ''}")
        if m:
            hata = f"araç koşamadı ({m.group(0)}) — {hata}"
        if "timed out" in (err or "").lower():
            hata = f"zaman aşımı ({butce}s)\n\n{zaman_asimi_notu(butce)}"
        return out, hata
    if not (out or "").strip():
        return "", "codex boş yanıt döndürdü"
    return out, ""


def yorum_dus(pr, govde):
    kod, _o, err = _kos("gh", "pr", "comment", str(pr), "--body-file", "-",
                        girdi=govde)
    return kod == 0, err


def _incele_bir_kez(pr, base):
    """Tek Codex turu — ayrıştırma ve tutarlılık dahil."""
    ham, hata = codex_incele(pr, base=base)
    bulgular, sonuc, okunabildi = bulgulari_ayikla(ham)
    return {"ham": ham, "hata": hata, "bulgular": bulgular, "sonuc": sonuc,
            "okunabildi": okunabildi,
            "tutarli": tutarli_mi(bulgular, sonuc) if okunabildi else False}


def _incele_yeniden_deneyerek(pr, base):
    """Okunamayan/tutarsız çıktıyı BİR KEZ daha sorar.

    Ölçüm: 62 ENGEL'in 16'sı bulgu değil BİÇİM hatasıydı (9 ayrıştırılamadı,
    7 tutarsız). Bir Codex çağrısı ~150s; kaçırılan tur medyan 16 dk. İkinci
    deneme de okunamazsa fail-closed korunur — 'okunamadı' hâlâ 'temiz'
    değildir, yalnız araç hatası bir insan turuna mal olmaz.

    ÇAĞRI BAŞARISIZSA yeniden DENENMEZ. Zaman aşımı, sıfırdan farklı çıkış ve
    boş yanıt biçim sorunu değildir; onları hemen tekrarlamak bir bütçe daha
    yakar (900s → 1800s) ve asılı sürecin üstüne ikincisini yığar. Bu satır
    ölçümle geldi: kapı kendi PR'ında (#48) 15 dk bütçeye dayandı ve yeniden
    deneme onu 30 dk yapacaktı. Zaman aşımının çaresi tekrar değil,
    `zaman_asimi_notu`nun yazdığı sıradır (asılı `codex exec`i öldür → bütçeyi
    yükselt → PR'ı böl).
    """
    d = _incele_bir_kez(pr, base)
    if (d["okunabildi"] and d["tutarli"]) or d["hata"]:
        return d, False
    ikinci = _incele_bir_kez(pr, base)
    if ikinci["okunabildi"] and ikinci["tutarli"]:
        return ikinci, True
    d["hata"] = f"{d['hata'] or 'SONUC satırı yok'} (2 deneme)"
    return d, True


def topla(pr):
    """PR'a dair tüm dış bilgiyi tek yerde toplar (main sade kalsın)."""
    ci_yesil, ci_ozet = ci_durumu(pr)
    # İncelenen commit BURADA sabitlenir; merge sonra bunu doğrular.
    head_sha = pr_head_sha(pr)
    onceki = marker_oku(pr_yorumlari(pr))
    ortak = {"risk": birlesik_risk(pr_dosyalari(pr), pr_diff(pr), pr=pr),
             "ci_yesil": ci_yesil, "ci_ozet": ci_ozet, "head_sha": head_sha,
             "tur": onceki["tur"] + 1, "degismedi": False, "yeniden": False,
             "artimli": False}

    if degismedi_mi(onceki, head_sha):
        # Codex hiç çağrılmaz: yeni commit yokken yeni bilgi de yoktur.
        return dict(ortak, degismedi=True, sonuc="", hata="", ham_kuyruk="",
                    bulgular={"P0": [], "P1": [], "P2": []},
                    okunabildi=True, tutarli=True, enjeksiyon=False,
                    p0gecmis=onceki["p0gecmis"])

    base = artimli_base(onceki)
    d, yeniden = _incele_yeniden_deneyerek(pr, base)
    return dict(
        ortak, yeniden=yeniden, artimli=bool(base),
        enjeksiyon=enjeksiyon_var_mi(pr_diff(pr)),
        bulgular=d["bulgular"], sonuc=d["sonuc"],
        okunabildi=d["okunabildi"], tutarli=d["tutarli"], hata=d["hata"],
        # P0 geçmişi SÖNMEZ: bir kez görülen PR tam diff'te kalır.
        p0gecmis=onceki["p0gecmis"] or bool(d["bulgular"]["P0"]),
        # Ayrıştırılamayan çıktının kuyruğu: teşhis için tek ipucu.
        ham_kuyruk="\n".join((d["ham"] or "").strip().splitlines()[-6:]))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pr")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--kuru", action="store_true", help="PR'a yorum atma")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    d = topla(a.pr)
    risk, ci_ozet, head_sha = d["risk"], d["ci_ozet"], d["head_sha"]
    bulgular, sonuc, enjeksiyon = d["bulgular"], d["sonuc"], d["enjeksiyon"]
    k, gerekce = karar(risk, bulgular, d["ci_yesil"], d["okunabildi"],
                       tutarli=d["tutarli"], enjeksiyon=enjeksiyon,
                       tur=d["tur"], degismedi=d["degismedi"],
                       hata=d.get("hata", ""))
    if not d["okunabildi"]:
        gerekce += f" — {d['hata'] or 'SONUC satırı yok'}"

    govde = ozet_govde(risk, bulgular, sonuc, k, gerekce, ci_ozet,
                       enjeksiyon,
                       tani="" if d["okunabildi"] else d["ham_kuyruk"],
                       tur=d["tur"], head_sha=head_sha,
                       p0gecmis=d["p0gecmis"], artimli=d["artimli"],
                       yeniden=d["yeniden"],
                       incelendi=d["okunabildi"] and d["tutarli"])
    if not a.kuru:
        ok, err = yorum_dus(a.pr, govde)
        if not ok:
            print(f"UYARI: PR yorumu düşülemedi: {err[:120]}", file=sys.stderr)

    if a.json:
        print(json.dumps({"pr": a.pr, "risk": risk, "ci": ci_ozet,
                          "karar": k, "gerekce": gerekce,
                          "bulgular": bulgular, "sonuc": sonuc,
                          "tur": d["tur"], "tavan": TUR_TAVANI,
                          "artimli": d["artimli"], "yeniden": d["yeniden"]},
                         ensure_ascii=False, indent=2))
    else:
        print(govde)

    if a.merge and _merge_et(a.pr, k, gerekce, head_sha) != 0:
        return 1
    return 0 if k != "engel" else 1


def _merge_et(pr, k, gerekce, head_sha):
    """Merge adımı — yalnız karar 'merge' ise. (0 = birleşti)"""
    if k != "merge":
        print(f"\nMERGE YAPILMADI — karar '{k}': {gerekce}")
        return 1
    try:
        komut = merge_komutu(pr, head_sha)
    except ValueError as e:
        print(f"\nMERGE YAPILMADI — {e}")
        return 1
    kod, _o, err = _kos(*komut)
    if kod != 0:
        # --match-head-commit uyuşmazsa: inceleme sonrası yeni commit
        # gelmiş demektir; İNCELENMEMİŞ kod birleşmez.
        print(f"merge başarısız (head değişmiş olabilir): {err[:200]}")
        return 1
    print(f"\nPR #{pr} merge edildi — incelenen commit {head_sha[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
