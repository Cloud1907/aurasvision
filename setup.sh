#!/usr/bin/env bash
# AurasVision kurulum betiği — sıfırdan çalışır sisteme.
#
# Kullanım:
#   ./setup.sh                 # kurulum + altyapı + duman testi
#   ./setup.sh --systemd       # ayrıca servisleri kur ve başlat (kalıcı çalışma)
#   ./setup.sh --no-docker     # db/redis/go2rtc başka yerdeyse altyapıyı atla
#   ./setup.sh --check         # hiçbir şey kurmaz, mevcut kurulumu denetler
#
# Tasarım: TEKRAR ÇALIŞTIRILABİLİR. Var olanı bozmaz, eksik olanı tamamlar.
# .env varsa dokunulmaz (token yeniden üretilmez — üretilse tüm istemciler düşerdi).
set -euo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$KOK"

SYSTEMD=0; DOCKER=1; SADECE_KONTROL=0
for a in "$@"; do
  case "$a" in
    --systemd) SYSTEMD=1 ;;
    --no-docker) DOCKER=0 ;;
    --check) SADECE_KONTROL=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Bilinmeyen seçenek: $a (--help)"; exit 2 ;;
  esac
done

ye() { printf '\033[32m✓\033[0m %s\n' "$1"; }
uy() { printf '\033[33m!\033[0m %s\n' "$1"; }
ha() { printf '\033[31m✗\033[0m %s\n' "$1"; }
bas() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# ── 0. Ön koşullar ────────────────────────────────────────────────
bas "0/6  Ön koşullar"
eksik=0
for k in python3 docker; do
  if command -v "$k" >/dev/null 2>&1; then ye "$k bulundu"
  else ha "$k YOK"; eksik=1; fi
done
PY_SURUM=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "0.0")
if [ "$(printf '%s\n3.11\n' "$PY_SURUM" | sort -V | head -1)" = "3.11" ]; then
  ye "python $PY_SURUM (>=3.11)"
else
  ha "python 3.11+ gerekli (bulunan: $PY_SURUM)"; eksik=1
fi
if docker compose version >/dev/null 2>&1; then ye "docker compose eklentisi"
elif [ "$DOCKER" = 1 ]; then uy "docker compose yok — --no-docker ile atlayabilirsin"; fi
# Docker grup erişimi: yoksa sg ile sarmalarız (yeniden oturum açmaya gerek kalmasın)
DC="docker compose"
if [ "$DOCKER" = 1 ] && ! docker info >/dev/null 2>&1; then
  if id -nG "$USER" | grep -qw docker; then
    uy "docker grubu oturuma yansımamış — sg docker ile sarmalanıyor"
    DC="sg docker -c 'docker compose"
  else
    ha "docker'a erişilemiyor. Çalıştır: sudo usermod -aG docker $USER && yeniden giriş yap"; eksik=1
  fi
fi
[ "$eksik" = 0 ] || { ha "Ön koşullar eksik — kurulum durdu"; exit 1; }

if [ "$SADECE_KONTROL" = 1 ]; then
  bas "Denetim modu — kurulum yapılmayacak"
fi

# ── 1. Python ortamı ──────────────────────────────────────────────
bas "1/6  Python ortamı"
if [ "$SADECE_KONTROL" = 0 ]; then
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/pip install -q -U pip
  .venv/bin/pip install -q -r requirements.txt
fi
if [ -x .venv/bin/python ]; then ye "venv hazır ($(.venv/bin/python -V 2>&1))"; else ha "venv yok"; exit 1; fi

# ── 2. Gizli bilgiler (.env) ──────────────────────────────────────
bas "2/6  Yapılandırma"
if [ -f .env ]; then
  ye ".env mevcut — dokunulmadı (token korunuyor)"
elif [ "$SADECE_KONTROL" = 0 ]; then
  TOKEN=$(.venv/bin/python -c 'import secrets;print(secrets.token_urlsafe(24))')
  cat > .env <<EOF
# AurasVision — gizli bilgiler. GIT'E GİRMEZ.
# Erişim anahtarı: paneldeki tüm /api ve /media isteklerinde zorunlu.
AURAS_TOKEN=$TOKEN
DATABASE_URL=postgresql://auras:auras@localhost:5433/auras
REDIS_URL=redis://localhost:6379/0
EOF
  chmod 600 .env
  ye ".env üretildi — erişim anahtarı rastgele oluşturuldu"
else
  uy ".env yok (denetim modunda üretilmedi)"
fi

# ── 3. Altyapı (Docker) ───────────────────────────────────────────
bas "3/6  Altyapı servisleri"
if [ "$DOCKER" = 1 ] && [ "$SADECE_KONTROL" = 0 ]; then
  if [ "$DC" = "docker compose" ]; then
    docker compose up -d db redis go2rtc >/dev/null
  else
    sg docker -c "docker compose up -d db redis go2rtc" >/dev/null
  fi
  ye "db · redis · go2rtc başlatıldı"
  printf '   veritabanı bekleniyor'
  for _ in $(seq 1 30); do
    if .venv/bin/python - <<'PY' 2>/dev/null
import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_URL", "postgresql://auras:auras@localhost:5433/auras")
from src.config import load_config
from src.store import open_store
s = open_store(load_config()); s.latest_health(); s.close()
PY
    then printf '\n'; ye "veritabanı hazır"; break; fi
    printf '.'; sleep 2
  done
else
  uy "altyapı atlandı (--no-docker veya --check)"
fi

# ── 4. Modeller ───────────────────────────────────────────────────
bas "4/6  Modeller"
[ -f yolo11n.pt ] || [ -f yolo11s.pt ] && ye "YOLO ağırlığı var" || \
  uy "YOLO ağırlığı yok — ilk çalıştırmada indirilir (internet gerekir)"
[ -f yolo11s.engine ] && ye "TensorRT engine var" || \
  uy "TensorRT engine yok. GPU'da üret: .venv/bin/yolo export model=yolo11s.pt format=engine half=True dynamic=True batch=32"

# ── 5. Duman testi ────────────────────────────────────────────────
bas "5/6  Duman testi"
if .venv/bin/python -m pytest tests/ -q >/dev/null 2>&1; then
  ye "birim testleri geçti"
else
  ha "birim testleri BAŞARISIZ — kurulumu tamamlamadan incele: .venv/bin/python -m pytest tests/ -q"
fi

# ── 6. Servisleştirme ─────────────────────────────────────────────
bas "6/6  Servisler"
if [ "$SYSTEMD" = 1 ] && [ "$SADECE_KONTROL" = 0 ]; then
  if [ "$KOK" != "/opt/aurasvision" ]; then
    uy "Unit dosyaları /opt/aurasvision yolunu varsayar; buradaki kurulum: $KOK"
    uy "systemd kurulumu ATLANDI — kodu /opt/aurasvision'a taşıyıp tekrar çalıştır"
  else
    sudo cp deploy/aurasvision-*.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now aurasvision-server aurasvision-worker \
                                aurasvision-ingestor aurasvision-recorder
    ye "servisler kuruldu ve başlatıldı"
    systemctl is-active --quiet aurasvision-recorder \
      && ye "kayıt servisi aktif (mevzuat gereği zorunlu)" \
      || ha "KAYIT SERVİSİ ÇALIŞMIYOR — saklama yükümlülüğü karşılanmaz"
  fi
else
  uy "servisleştirme yapılmadı (--systemd ile açılır)"
  echo "   Elle çalıştırma:"
  echo "     set -a; . ./.env; set +a"
  echo "     .venv/bin/python -m src.server     # panel"
  echo "     .venv/bin/python -m src.worker     # sürekli analiz"
  echo "     .venv/bin/python -m src.ingestor   # olay yazıcı"
  echo "     .venv/bin/python -m src.recorder   # sürekli kayıt"
fi

# ── Özet ──────────────────────────────────────────────────────────
bas "Kurulum özeti"
PORT=$(.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from src.config import load_config; print(load_config().get('server.port',8000))" 2>/dev/null || echo 8000)
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "  Panel      : http://${IP:-127.0.0.1}:$PORT"
if [ -f .env ]; then
  echo "  Anahtar    : $(grep -E '^AURAS_TOKEN=' .env | cut -d= -f2-)"
  echo "               (tek tık giriş: http://${IP:-127.0.0.1}:$PORT/?token=ANAHTAR)"
fi
echo "  Kayıt yolu : output/rec  ·  saklama: config.yaml → record.keep_days"
echo
echo "  Sonraki adım: panele gir → Kameralar → Kamera ekle → IP ile sorgula (ONVIF)"
echo "  Kurulum kılavuzu: docs/KURULUM.md"
