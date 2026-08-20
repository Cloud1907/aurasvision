#!/usr/bin/env bash
# Git kancalarini kurar. Yeni makinede repo klonlandiginda bir kez calistir.
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)

# Kanca dizini "$ROOT/.git/hooks" DEGILDIR — iki ayri sebeple:
#   1. worktree'de `.git` bir DOSYADIR (ana depoya isaretci). Sabit yol
#      "install: .../.git/hooks/...: Not a directory" ile coker; kapi
#      worktree'den KURULAMAZ. Kancalar zaten ana deponun ORTAK dizininde
#      durur, tum worktree'ler onu paylasir.
#   2. core.hooksPath ayarliysa git .git/hooks'a hic BAKMAZ. Oraya kurmak
#      sessiz bir hiclik olurdu: script "kuruldu" der, kapi hic kosmaz —
#      koruma illuzyonu kapinin yoklugundan beterdir.
# Ikisini de git'in kendisi cozer. Bulgu 2026-08-07, PR #17.
HOOKS=$(cd "$ROOT" && git rev-parse --git-path hooks)
case "$HOOKS" in /*) ;; *) HOOKS="$ROOT/$HOOKS" ;; esac

mkdir -p "$HOOKS"
install -m 755 "$ROOT/bin/hooks/pre-push" "$HOOKS/pre-push"
echo "pre-push kancasi kuruldu: $HOOKS/pre-push"
