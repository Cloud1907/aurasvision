# AurasVision — Windows kurulum betiği.
# Kullanıcı bunu doğrudan çalıştırmaz; AurasVision-Kurulum.bat çift tıklanır.
#
# Tasarım: TEKRAR ÇALIŞTIRILABİLİR. Var olanı bozmaz, eksik olanı tamamlar.
# .env varsa dokunulmaz (erişim anahtarı yeniden üretilseydi tüm istemciler düşerdi).

param([switch]$NoLaunch)   # kurulum sihirbazı içinden çağrılırken paneli açma

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

# ── 2. Docker ─────────────────────────────────────────────────────
Bas "2/6  Docker Desktop"
$dockerVar = $false
try { docker info 2>&1 | Out-Null; if ($LASTEXITCODE -eq 0) { $dockerVar = $true } } catch { }
if ($dockerVar) {
    Ye "Docker çalışıyor"
} else {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Uy "Docker kurulu ama ÇALIŞMIYOR — Docker Desktop'ı başlatın, sonra bu kurulumu tekrar çalıştırın"
    } else {
        Uy "Docker Desktop yok — kuruluyor (winget). Kurulum sonrası BİLGİSAYARI YENİDEN BAŞLATIN."
        try {
            winget install -e --id Docker.DockerDesktop --accept-source-agreements --accept-package-agreements | Out-Null
            Ye "Docker Desktop kuruldu — yeniden başlatıp bu kurulumu tekrar çalıştırın"
        } catch {
            Uy "Docker kurulamadı. Elle kurun: https://www.docker.com/products/docker-desktop/"
        }
    }
    Uy "Docker olmadan veritabanı ve canlı izleme çalışmaz — kurulum yine de devam ediyor"
}

# ── 3. Python ortamı ──────────────────────────────────────────────
Bas "3/6  Bağımlılıklar"
if (-not (Test-Path ".venv")) { & $py -m venv .venv }
$vpy = Join-Path $Kok ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) { Ha "Sanal ortam kurulamadı"; exit 1 }
& $vpy -m pip install -q -U pip
& $vpy -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Ha "Bağımlılıklar kurulamadı"; exit 1 }
Ye "Bağımlılıklar kuruldu"

# ── 4. Yapılandırma ───────────────────────────────────────────────
Bas "4/6  Yapılandırma"
if (Test-Path ".env") {
    Ye ".env mevcut — dokunulmadı (erişim anahtarı korunuyor)"
    $token = (Select-String -Path ".env" -Pattern '^AURAS_TOKEN=(.*)$').Matches.Groups[1].Value
} else {
    $token = & $vpy -c "import secrets;print(secrets.token_urlsafe(24))"
    # Veritabanı seçimi Docker'ın GERÇEKTEN çalışmasına bağlı:
    #  * Docker var  → PostgreSQL + TimescaleDB + pgvector (konteynerde, ayrı kurulum yok)
    #  * Docker yok  → satırlar YAZILMAZ; uygulama SQLite'a düşer (kurulum gerektirmez).
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
# Docker kurulu olmadığı için veritabanı SQLite (output\aurasvision.db).
# Çok kameralı kurulumda Docker Desktop kurup aşağıdaki iki satırı açın:
# DATABASE_URL=postgresql://auras:auras@localhost:5433/auras
# REDIS_URL=redis://localhost:6379/0
"@ | Set-Content -Path ".env" -Encoding UTF8
        Ye "Erişim anahtarı üretildi · veritabanı: SQLite (kurulum gerektirmez)"
        Uy "Sürekli analiz (worker) için Redis gerekir — Docker kurulunca etkinleşir"
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

# ── 5. Altyapı ────────────────────────────────────────────────────
Bas "5/6  Altyapı servisleri"
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
    Uy "Docker çalışmadığı için altyapı atlandı"
}

# ── 6. Başlatıcılar ───────────────────────────────────────────────
Bas "6/6  Başlatma kısayolları"
# Uygulamayı başlatan betik — kullanıcı bunu çift tıklar
@"
@echo off
title AurasVision
cd /d "%~dp0.."
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
)
start "" http://127.0.0.1:8000/?token=$token
if not exist output\logs mkdir output\logs
start "AurasVision Sunucu" /min cmd /c ".venv\Scripts\python.exe -m src.server 1>>output\logs\sunucu-konsol.log 2>&1"
timeout /t 3 >nul
start "AurasVision Kayit" /min cmd /c ".venv\Scripts\python.exe -m src.recorder 1>>output\logs\kayit-konsol.log 2>&1"
start "AurasVision Analiz" /min cmd /c ".venv\Scripts\python.exe -m src.worker 1>>output\logs\analiz-konsol.log 2>&1"
start "AurasVision Olaylar" /min cmd /c ".venv\Scripts\python.exe -m src.ingestor 1>>output\logs\olaylar-konsol.log 2>&1"
echo AurasVision calisiyor. Bu pencereyi kapatabilirsiniz.
timeout /t 5 >nul
"@ | Set-Content -Path "windows\AurasVision-Baslat.bat" -Encoding ASCII

@"
@echo off
title AurasVision Durdur
taskkill /F /IM python.exe /FI "WINDOWTITLE eq AurasVision*" >nul 2>&1
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

# Kurulum bitince paneli aç
if ($dockerVar -and -not $NoLaunch) {
    Start-Process (Join-Path $Kok "windows\AurasVision-Baslat.bat")
}
