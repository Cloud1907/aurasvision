#!/usr/bin/env bash
# Capraz-vendor risk sinyali: diff'i Codex'e inceletir, PR'a yorum olarak duser.
#
# Kullanim:
#   bin/codex-review.sh                 # aktif dalin main'e gore diff'i, PR'a yorum
#   bin/codex-review.sh 12              # 12 numarali PR'in diff'i
#   bin/codex-review.sh 12 --base=SHA   # ARTIMLI: yalniz SHA'dan beri gelen
#   bin/codex-review.sh --dry-run       # yorum atmaz, ekrana basar
#
# NOT: Bu bir RISK SINYALIDIR, makine kaniti degildir (AGENTS.md).
set -euo pipefail

BRIDGE="$HOME/.claude/skills/codex-debate/bin/ask-codex.sh"
DRY_RUN=0
PR=""
BASE=""

# SIRA ONEMLI: --base=SHA rakam icerir, `*[0-9]*` dalindan ONCE eslesmeli.
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --base=*) BASE="${arg#--base=}" ;;
    *[0-9]*) PR="$arg" ;;
  esac
done

if [ ! -x "$BRIDGE" ]; then
  echo "HATA: codex koprusu yok: $BRIDGE" >&2
  exit 2
fi

if [ -n "$PR" ] && [ -n "$BASE" ]; then
  # ARTIMLI inceleme. `gh pr diff` her tur TUM birikmis diff'i verir; bir
  # P1'i duzelten kod bir sonraki turun inceleme yuzeyi olur ve orada yeni
  # bir P1 dogar (olcum 2026-08-12: 9 PR'da 62 tur). compare API'si secilir
  # cunku PR head'i yerelde fetch edilmis olmayabilir.
  REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
  HEAD_SHA=$(gh pr view "$PR" --json headRefOid -q .headRefOid)
  DIFF=$(gh api "repos/$REPO/compare/$BASE...$HEAD_SHA" \
           -H "Accept: application/vnd.github.v3.diff") || DIFF=""
  if [ -z "$DIFF" ]; then
    # Force-push BASE'i yok etmis ya da yeni commit hicbir sey degistirmemis
    # olabilir. TAM diff'e dusmek her zaman guvenli yondur: daha GENIS
    # inceleme, daha dar degil. Bos artimli diff'i "temiz" saymak, onceki
    # turun bulgusunu sessizce silerdi.
    echo "Artimli diff alinamadi/bos — tam diff'e dusuluyor." >&2
    DIFF=$(gh pr diff "$PR")
  fi
elif [ -n "$PR" ]; then
  DIFF=$(gh pr diff "$PR")
else
  BASE=$(git merge-base HEAD origin/main 2>/dev/null || git rev-parse HEAD~1)
  DIFF=$(git diff "$BASE"...HEAD)
fi

if [ -z "$DIFF" ]; then
  echo "Diff bos — inceleyecek degisiklik yok."
  exit 0
fi

PROMPT_FILE=$(mktemp)
trap 'rm -f "$PROMPT_FILE"' EXIT

cat > "$PROMPT_FILE" <<EOF
Sen bagimsiz bir kod inceleyicisisin. Asagidaki diff'i incele.

Kurallar:
- YALNIZ dogrulugu, guvenligi veya veri butunlugunu etkileyen bulgulari raporla.
- Stil, isimlendirme, "daha iyi olabilirdi" turu yorum YAPMA — gurultu uretme.
- Her bulgu: [P0|P1|P2] dosya:satir — sorun — somut istismar/hata senaryosu.
- P0 = merge engelleyici, P1 = merge oncesi duzeltilmeli, P2 = bilgi.
- Bulgu yoksa acikca TEMIZ yaz. Bulgu uydurma.
- Sonuna tek satirlik hukum: SONUC: TEMIZ veya SONUC: N bulgu (en yuksek: PX).

## Diff
$DIFF
EOF

echo "Codex inceliyor..." >&2
OUT=$("$BRIDGE" < "$PROMPT_FILE")

BODY="## Codex incelemesi (risk sinyali)

$OUT

---
Bu bir capraz-vendor risk sinyalidir, makine kaniti degildir. Merge kosulu: CI yesil + insan karari."

if [ "$DRY_RUN" -eq 1 ]; then
  printf '%s\n' "$BODY"
  exit 0
fi

if [ -n "$PR" ]; then
  printf '%s' "$BODY" | gh pr comment "$PR" --body-file -
  echo "PR #$PR uzerine yorum dusuldu."
else
  printf '%s' "$BODY" | gh pr comment --body-file - 2>/dev/null \
    || { echo "Acik PR bulunamadi; ciktinin kendisi:"; printf '%s\n' "$BODY"; }
fi
