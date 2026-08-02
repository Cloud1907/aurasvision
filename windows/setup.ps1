# AurasVision — Windows kurulum betiği.
# Kullanıcı bunu doğrudan çalıştırmaz; AurasVision-Kurulum.bat çift tıklanır.
#
# Tasarım: TEKRAR ÇALIŞTIRILABİLİR. Var olanı bozmaz, eksik olanı tamamlar.
# .env varsa dokunulmaz (erişim anahtarı yeniden üretilseydi tüm istemciler düşerdi).
#
# Adım sırası bilinçli: yapılandırma ve başlatma kısayolları ÖNCE, ağır/kırılgan
# bağımlılık kurulumu SONRA. İlk saha denemesinde pip adımı yarıda kalınca
# masaüstü kısayolu var olmayan bir .bat'a işaret ediyordu — kısayolun hedefi
# artık her koşulda üretiliyor ve kurulum eksikse kullanıcıya bunu söylüyor.

param(
    [switch]$NoLaunch,   # kurulum sihirbazı içinden çağrılırken paneli açma
    [switch]$Buyuk       # 30+ kamera: PostgreSQL + Redis (Docker Desktop gerekir)
)

# İki kurulum profili var:
#
#   Tek makine (VARSAYILAN) — Docker YOK. Veritabanı SQLite, canlı izleme
#     go2rtc'nin kendi .exe'si, olaylar worker'dan doğrudan veritabanına.
#     Yeniden başlatma gerekmez, lisans sorunu yoktur, tek geçişte biter.
#
#   Büyük kurulum (-Buyuk) — Docker Desktop + PostgreSQL/TimescaleDB + Redis.
#     Çok worker'a bölünebilir; 30+ kamerada gereklidir.
#
# Varsayılanın Docker olmaması bilinçli: Docker Desktop ilk kurulumda Windows'u
# yeniden başlatmaya zorlar (kurulum ikiye bölünür) ve büyük şirketlerde ücretli
# lisans ister. Küçük kurulumda ikisinin de karşılığı yok.

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Kok

function Ye($m) { Write-Host "  [OK] $m" -ForegroundColor Green }
function Uy($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }
function Ha($m) { Write-Host "  [X]  $m" -ForegroundColor Red }
function Bas($m) { Write-Host ""; Write-Host $m -ForegroundColor Cyan }

Write-Host ""
Write-Host "  AurasVision — Görüntü Analitiği Platformu" -ForegroundColor White
Write-Host "  Kurulum başlıyor. Bu işlem birkaç dakika sürebilir." -ForegroundColor DarkGray
Write-Host "  Kurulum dizini: $Kok" -ForegroundColor DarkGray

# ── 1. Python ─────────────────────────────────────────────────────
Bas "1/6  Python"
$py = $null
foreach ($aday in @("python", "python3", "py")) {
    try {
        $s = & $aday -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
        if ($s -and [version]$s -ge [version]"3.11") { $py = $aday; Ye "Python $s bulundu"; break }
    } catch { }
}
if (-not $py) {
    Uy "Python 3.11+ bulunamadı — otomatik kuruluyor (winget)"
    try {
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements | Out-Null
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [Environment]::GetEnvironmentVariable("Path", "User")
        $py = "python"
        Ye "Python kuruldu"
    } catch {
        Ha "Python kurulamadı. Elle kurun: https://www.python.org/downloads/ (kurulumda 'Add to PATH' işaretleyin)"
        exit 1
    }
}

# ── 2. Altyapı ────────────────────────────────────────────────────
Bas "2/6  Altyapı"
$dockerVar = $false
if ($Buyuk) {
    try { docker info 2>&1 | Out-Null; if ($LASTEXITCODE -eq 0) { $dockerVar = $true } } catch { }
    if ($dockerVar) {
        Ye "Docker çalışıyor — PostgreSQL + Redis kullanılacak"
    } elseif (Get-Command docker -ErrorAction SilentlyContinue) {
        Uy "Docker kurulu ama çalışmıyor — Docker Desktop'ı başlatıp kurulumu tekrarlayın"
    } else {
        Uy "Docker Desktop kuruluyor. Kurulum bitince BİLGİSAYARI YENİDEN BAŞLATIN ve bu kurulumu tekrar çalıştırın."
        try {
            winget install -e --id Docker.DockerDesktop --accept-source-agreements --accept-package-agreements | Out-Null
            Ye "Docker Desktop kuruldu"
        } catch {
            Uy "Docker kurulamadı. Elle kurun: https://www.docker.com/products/docker-desktop/"
        }
    }
    if (-not $dockerVar) { Uy "Docker hazır değil — kurulum tek makine profiline düşüyor" }
}

# Canlı izleme fan-out'u: go2rtc. Docker'lı kurulumda konteyner, tek makinede
# kendi .exe'si (tek dosya, kurulum gerektirmez).
$go2rtcExe = Join-Path $Kok "bin\go2rtc.exe"
if (-not $dockerVar) {
    if (Test-Path $go2rtcExe) {
        Ye "Canlı izleme bileşeni mevcut"
    } else {
        New-Item -ItemType Directory -Force -Path (Join-Path $Kok "bin") | Out-Null
        $zip = Join-Path $env:TEMP "go2rtc_win64.zip"
        try {
            Invoke-WebRequest -UseBasicParsing -OutFile $zip `
                "https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_win64.zip"
            Expand-Archive -Path $zip -DestinationPath (Join-Path $Kok "bin") -Force
            Remove-Item $zip -ErrorAction SilentlyContinue
            if (Test-Path $go2rtcExe) { Ye "Canlı izleme bileşeni kuruldu" }
            else { Uy "Canlı izleme bileşeni açılamadı — anlık görüntü kipine düşülecek" }
        } catch {
            Uy "Canlı izleme bileşeni indirilemedi — anlık görüntü kipine düşülecek"
        }
    }
    Ye "Profil: tek makine (SQLite · Docker gerekmez)"
}

# ── 3. Yapılandırma ───────────────────────────────────────────────
Bas "3/6  Yapılandırma"
if (Test-Path ".env") {
    Ye ".env mevcut — dokunulmadı (erişim anahtarı korunuyor)"
    $token = (Select-String -Path ".env" -Pattern '^AURAS_TOKEN=(.*)$').Matches.Groups[1].Value
} else {
    # Anahtar PowerShell'in kendi kripto RNG'siyle üretilir — Python'a bağımlı
    # değil; sanal ortam kurulamasa bile yapılandırma tamamlanır.
    $rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::new()
    $b = New-Object byte[] 24; $rng.GetBytes($b)
    $token = ([Convert]::ToBase64String($b)) -replace '[+/=]', ''
    # Veritabanı seçimi Docker'ın GERÇEKTEN çalışmasına bağlı:
    #  * Docker var  → PostgreSQL + TimescaleDB + pgvector (konteynerde, ayrı kurulum yok)
    #  * Docker yok  → satırlar YAZILMAZ; uygulama SQLite'a, worker da tek makine
    #                  kipine düşer (olayları doğrudan veritabanına yazar).
    # Adresi körlemesine yazmak, Docker yokken "bağlanamıyor" hatası demekti.
    if ($dockerVar) {
        @"
# AurasVision — gizli bilgiler. Bu dosyayı paylaşmayın.
AURAS_TOKEN=$token
DATABASE_URL=postgresql://auras:auras@localhost:5433/auras
REDIS_URL=redis://localhost:6379/0
"@ | Set-Content -Path ".env" -Encoding UTF8
        Ye "Erişim anahtarı üretildi · veritabanı: PostgreSQL (Docker)"
    } else {
        @"
# AurasVision — gizli bilgiler. Bu dosyayı paylaşmayın.
AURAS_TOKEN=$token
# Tek makine profili: veritabanı SQLite (output\aurasvision.db), olaylar
# analiz servisinden doğrudan veritabanına yazılır.
# 30+ kameraya çıkarken kurulumu -Buyuk ile tekrar çalıştırın; o zaman
# aşağıdaki iki satır otomatik eklenir:
# DATABASE_URL=postgresql://auras:auras@localhost:5433/auras
# REDIS_URL=redis://localhost:6379/0
"@ | Set-Content -Path ".env" -Encoding UTF8
        Ye "Erişim anahtarı üretildi · veritabanı: SQLite (kurulum gerektirmez)"
    }
}

# GPU yoksa hafif modele düş — TensorRT engine donanıma özeldir, taşınmaz
$gpu = $false
try { if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { nvidia-smi | Out-Null; $gpu = ($LASTEXITCODE -eq 0) } } catch { }
if ($gpu) {
    Ye "NVIDIA GPU bulundu"
    Uy "TensorRT motoru bu makinede üretilmeli: .venv\Scripts\yolo export model=yolo11s.pt format=engine half=True dynamic=True batch=32"
} else {
    Uy "GPU yok — CPU modeline geçiliyor (yavaş ama çalışır)"
    (Get-Content "config.yaml") `
        -replace '^(\s*)model: yolo11s\.engine', '$1model: yolo11n.pt' `
        -replace '^(\s*)engine: nvdec', '$1engine: ultralytics' |
        Set-Content "config.yaml" -Encoding UTF8
}

# ── 4. Başlatıcılar ───────────────────────────────────────────────
# BİLEREK bağımlılık kurulumundan ÖNCE: pip yarıda kalsa bile masaüstü kısayolu
# çalışır bir hedefe işaret eder; hedef, kurulum eksikse bunu kullanıcıya söyler.
Bas "4/6  Başlatma kısayolları"
# Hangi servislerin başlayacağı kurulum profiline bağlı:
#   Docker'lı  → olay yolu Redis'te, ingestor gerekir; go2rtc konteynerde
#   Tek makine → worker doğrudan veritabanına yazar; go2rtc kendi .exe'si
if ($dockerVar) {
    $olaylar  = 'start "AurasVision Olaylar" /min cmd /c ".venv\Scripts\python.exe -m src.ingestor 1>>output\logs\olaylar-konsol.log 2>&1"'
    $canli    = ''
} else {
    $olaylar  = 'rem tek makine profili: olaylar analiz servisinden dogrudan veritabanina yazilir'
    $canli    = @'
if not exist go2rtc\go2rtc.yaml (mkdir go2rtc 2>nul & type nul > go2rtc\go2rtc.yaml)
if exist bin\go2rtc.exe start "AurasVision Canli" /min cmd /c "bin\go2rtc.exe -config go2rtc\go2rtc.yaml 1>>output\logs\canli-konsol.log 2>&1"
'@
}
@"
@echo off
title AurasVision
cd /d "%~dp0.."
rem .env'i Python kendisi okur (src/config.py load_env). Burada ayrica ayristirmak
rem gereksiz ve riskliydi: yorum satirindaki bir parantez for blogunu erken kapatiyordu.
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  AurasVision kurulumu tamamlanmamis gorunuyor: Python ortami eksik.
  echo  Lutfen kurulumu tekrar calistirin:
  echo    windows\AurasVision-Kurulum.bat  ^(sag tik - Yonetici olarak calistir^)
  echo.
  pause
  exit /b 1
)
if not exist output\logs mkdir output\logs
$canli
start "" http://127.0.0.1:8000/?token=$token
start "AurasVision Sunucu" /min cmd /c ".venv\Scripts\python.exe -m src.server 1>>output\logs\sunucu-konsol.log 2>&1"
timeout /t 3 >nul
start "AurasVision Kayit" /min cmd /c ".venv\Scripts\python.exe -m src.recorder 1>>output\logs\kayit-konsol.log 2>&1"
start "AurasVision Analiz" /min cmd /c ".venv\Scripts\python.exe -m src.worker 1>>output\logs\analiz-konsol.log 2>&1"
$olaylar
echo AurasVision calisiyor. Bu pencereyi kapatabilirsiniz.
timeout /t 5 >nul
"@ | Set-Content -Path "windows\AurasVision-Baslat.bat" -Encoding ASCII

@"
@echo off
title AurasVision Durdur
taskkill /F /IM python.exe /FI "WINDOWTITLE eq AurasVision*" >nul 2>&1
taskkill /F /IM go2rtc.exe >nul 2>&1
echo AurasVision durduruldu.
timeout /t 3 >nul
"@ | Set-Content -Path "windows\AurasVision-Durdur.bat" -Encoding ASCII
Ye "Başlat / Durdur kısayolları oluşturuldu"

# Masaüstü kısayolu — kullanıcı klasör aramasın
try {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut([Environment]::GetFolderPath("Desktop") + "\AurasVision.lnk")
    $lnk.TargetPath = Join-Path $Kok "windows\AurasVision-Baslat.bat"
    $lnk.WorkingDirectory = $Kok
    $lnk.Description = "AurasVision görüntü analitiği panelini başlat"
    $lnk.Save()
    Ye "Masaüstü kısayolu oluşturuldu"
} catch { Uy "Masaüstü kısayolu oluşturulamadı (elle: windows\AurasVision-Baslat.bat)" }

# Windows açılışında otomatik başlat
try {
    $gorev = "AurasVision"
    schtasks /Query /TN $gorev >$null 2>&1
    if ($LASTEXITCODE -ne 0) {
        schtasks /Create /TN $gorev /TR "`"$Kok\windows\AurasVision-Baslat.bat`"" `
                 /SC ONSTART /RL HIGHEST /RU SYSTEM /F | Out-Null
        Ye "Açılışta otomatik başlatma tanımlandı"
    } else { Ye "Açılış görevi zaten tanımlı" }
} catch { Uy "Otomatik başlatma tanımlanamadı — panel elle başlatılacak" }

# ── 5. Python ortamı ──────────────────────────────────────────────
# En kırılgan ve en uzun adım (torch ~2 GB iner). Bu yüzden en sonda:
# buraya gelene kadar yapılandırma ve kısayollar çoktan hazır.
Bas "5/6  Bağımlılıklar (en uzun adım — torch dahil, sabır)"
if (-not (Test-Path ".venv")) { & $py -m venv .venv }
$vpy = Join-Path $Kok ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) { Ha "Sanal ortam kurulamadı"; exit 1 }
& $vpy -m pip install -q -U pip
& $vpy -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Ha "Bağımlılıklar kurulamadı."
    Uy "İnternet bağlantısını kontrol edin ve kurulumu tekrar çalıştırın:"
    Uy "  windows\AurasVision-Kurulum.bat (sağ tık → Yönetici olarak çalıştır)"
    Uy "Sorun sürerse bu penceredeki hata satırını destek için kaydedin."
    exit 1
}
Ye "Bağımlılıklar kuruldu"

# ── 6. Altyapı servisleri ─────────────────────────────────────────
Bas "6/6  Altyapı servisleri"
if ($dockerVar) {
    docker compose up -d db redis go2rtc | Out-Null
    Ye "Veritabanı, olay yolu ve canlı izleme başlatıldı"
    Write-Host "     veritabanı bekleniyor..." -NoNewline
    for ($i = 0; $i -lt 30; $i++) {
        $env:DATABASE_URL = "postgresql://auras:auras@localhost:5433/auras"
        & $vpy -c "import sys;sys.path.insert(0,'.');from src.config import load_config;from src.store import open_store;s=open_store(load_config());s.latest_health();s.close()" 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Host ""; Ye "Veritabanı hazır"; break }
        Start-Sleep 2; Write-Host "." -NoNewline
    }
} else {
    # Tek makine: ayrı servis yok. go2rtc uygulama ile birlikte başlar,
    # veritabanı dosyası ilk açılışta kendini kurar.
    Ye "Ek servis gerekmiyor — veritabanı ve canlı izleme uygulama ile başlar"
}

# ── Özet ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ─────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  KURULUM TAMAMLANDI" -ForegroundColor Green
Write-Host ""
Write-Host "  Panel     : http://127.0.0.1:8000"
Write-Host "  Anahtar   : $token"
@"
AurasVision erisim anahtari
===========================
$token

Panel: http://127.0.0.1:8000
Tek tik giris: http://127.0.0.1:8000/?token=$token

Bu dosyayi guvenli tutun; anahtar panele erisim yetkisidir.
"@ | Set-Content -Path (Join-Path $Kok "ERISIM-ANAHTARI.txt") -Encoding UTF8
Write-Host ""
Write-Host "  Başlatmak için masaüstündeki AurasVision kısayoluna çift tıklayın."
Write-Host "  Panel tarayıcıda kendiliğinden açılır."
Write-Host ""
Write-Host "  İlk adım: Kameralar -> Kamera ekle -> kamera IP/kullanıcı/şifre -> IP ile sorgula"
Write-Host "  ─────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# Kurulum bitince paneli aç. Docker'lı profilde Docker gerçekten çalışmıyorsa
# başlatmak anlamsız (veritabanı yok); tek makine profilinde böyle bir koşul yok.
if ((-not $Buyuk -or $dockerVar) -and -not $NoLaunch) {
    Start-Process (Join-Path $Kok "windows\AurasVision-Baslat.bat")
}
