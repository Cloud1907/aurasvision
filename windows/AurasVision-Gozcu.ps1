# AurasVision — servis gözcüsü.
#
# Baslat.bat servisleri BİR KEZ başlatır; biri çökerse (kamera akışı bozuk,
# sürücü hatası, bellek) kimse geri getirmez ve panel sessizce boş kalır.
# Sahada en pahalı arıza tipi budur: sistem "açık" görünür, veri üretmez.
# Bu betik servisleri ayakta tutar ve her müdahaleyi loglar.
#
# Tek başına çalışır: eksikse başlatır, çalışıyorsa dokunmaz. İki kopyası
# aynı anda koşamaz (aşağıdaki tek-örnek kontrolü).
param([int]$Aralik = 30)

$ErrorActionPreference = "Continue"
$Kok = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Kok

$vpy    = Join-Path $Kok ".venv\Scripts\python.exe"
$logDir = Join-Path $Kok "output\logs"
$gunluk = Join-Path $logDir "gozcu.log"
New-Item -ItemType Directory -Force $logDir | Out-Null

function Yaz($m) {
    $satir = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
    Add-Content -Path $gunluk -Value $satir -Encoding utf8
}

# Tek örnek: ikinci gözcü aynı servisleri ikinci kez başlatırdı (çift worker =
# aynı kamerayı iki kez sayar, olaylar mükerrer).
#
# Kilit PID DOSYASI ile tutulur, komut satırı taramasıyla değil: gözcüyü başlatan
# sürecin (Start-Process ... -File ...\AurasVision-Gozcu.ps1) komut satırında da
# script adı geçiyor ve gözcü kendi başlatıcısını "zaten çalışan kopya" sanıp
# hiç açılmadan çıkıyordu.
$kilit = Join-Path $logDir "gozcu.pid"
if (Test-Path $kilit) {
    $eski = (Get-Content $kilit -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($eski) {
        # PID geri dönüştürülmüş olabilir — sürecin gerçekten powershell olduğunu doğrula
        $s = Get-Process -Id ([int]$eski) -ErrorAction SilentlyContinue
        if ($s -and $s.ProcessName -eq "powershell") {
            Yaz "gözcü zaten çalışıyor (PID $eski) — çıkılıyor"; exit 0
        }
    }
}
$PID | Set-Content -Path $kilit -Encoding ascii

if (-not (Test-Path $vpy)) { Yaz "HATA: .venv yok — önce windows\AurasVision-Kurulum.bat"; exit 1 }

# Olay yolu Redis'te mi? .env'de REDIS_URL varsa ingestor da gerekir; tek makine
# profilinde worker doğrudan veritabanına yazar, ingestor süreci HİÇ olmamalı.
$redisVar = $false
$envDosya = Join-Path $Kok ".env"
if (Test-Path $envDosya) {
    $redisVar = @(Get-Content $envDosya | Where-Object { $_ -match '^\s*REDIS_URL\s*=\s*\S' }).Count -gt 0
}

$servisler = @(
    @{ Ad = "sunucu"; Modul = "src.server";   Log = "sunucu-konsol.log" },
    @{ Ad = "analiz"; Modul = "src.worker";   Log = "analiz-konsol.log" },
    @{ Ad = "kayit";  Modul = "src.recorder"; Log = "kayit-konsol.log"  }
)
if ($redisVar) { $servisler += @{ Ad = "olaylar"; Modul = "src.ingestor"; Log = "olaylar-konsol.log" } }

# Yeniden başlatma fırtınası koruması: bozuk yapılandırmada süreç saniyede bir
# ölüp doğar, log şişer, CPU yanar. Üst üste 5 başarısız denemeden sonra o servis
# 10 dakika beklemeye alınır — diğerleri çalışmaya devam eder.
$hata = @{}; $bekle = @{}

# go2rtc yapılandırmasını SUNUCU üretir (kamera eklenince/silinince yeniden yazar),
# ama go2rtc dosyayı kendiliğinden okumaz ve /api/restart da yeniden okumuyor
# (ölçüldü: 200 döner, akışlar eski kalır). Gözcü go2rtc'yi sunucudan ÖNCE
# başlattığı için her açılışta bir tur eski yapılandırmayla koşuyordu: silinen
# kamera canlıda durmaya, yeni kamera görünmemeye devam ediyordu. Çözüm: dosyanın
# değişme zamanı izlenir, değiştiyse go2rtc yeniden başlatılır.
$go2rtcCfg = Join-Path $Kok "go2rtc\go2rtc.yaml"
$cfgZaman = $null

function SurecVarMi($modul) {
    $p = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -like "*-m $modul*" -or $_.CommandLine -like "*$modul*" })
    return $p.Count -gt 0
}

function Baslat($s) {
    # Konsol çıktısı cmd ile EKLENEREK yazılır (Start-Process -Redirect* dosyayı
    # her başlatmada sıfırlar; çöküş nedeni bir sonraki yeniden başlatmada silinirdi).
    # `cmd /s /c "..."`: /s olmadan cmd, tırnakla başlayan komutta tırnakları
    # kendi kurallarıyla ayıklıyor ve komut bozuluyordu — süreçler hiç doğmadı.
    $komut = '"{0}" -m {1} 1>>"{2}" 2>&1' -f $vpy, $s.Modul, (Join-Path $logDir $s.Log)
    Start-Process -WindowStyle Hidden -FilePath "cmd.exe" -ArgumentList "/s", "/c", "`"$komut`"" | Out-Null
}

Yaz "gözcü başladı (aralık $Aralik sn, servisler: $(($servisler | ForEach-Object { $_.Ad }) -join ', ')$(if ($redisVar) { '' } else { ' · tek makine' }))"

while ($true) {
    # go2rtc: canlı izleme fan-out'u. Docker profilinde konteynerde koşar,
    # tek makinede kendi .exe'si — yalnız ikili varsa bizim işimiz.
    $go2 = Join-Path $Kok "bin\go2rtc.exe"
    if (Test-Path $go2) {
        # Yapılandırma go2rtc çalışırken değiştiyse süreci düşür — döngünün altındaki
        # "çalışmıyorsa başlat" dalı onu yeni dosyayla geri getirir.
        if (Test-Path $go2rtcCfg) {
            $z = (Get-Item $go2rtcCfg).LastWriteTimeUtc
            if ($cfgZaman -and $z -gt $cfgZaman -and (Get-Process go2rtc -ErrorAction SilentlyContinue)) {
                Yaz "go2rtc yapılandırması değişti — akışlar yenileniyor"
                Get-Process go2rtc -ErrorAction SilentlyContinue | Stop-Process -Force
                Start-Sleep -Seconds 2
            }
            $cfgZaman = $z
        }
        if (-not (Get-Process go2rtc -ErrorAction SilentlyContinue)) {
            $cfg = Join-Path $Kok "go2rtc\go2rtc.yaml"
            if (-not (Test-Path $cfg)) { New-Item -ItemType Directory -Force (Split-Path $cfg) | Out-Null; New-Item -ItemType File $cfg -Force | Out-Null }
            $k = '"{0}" -config "{1}" 1>>"{2}" 2>&1' -f $go2, $cfg, (Join-Path $logDir "canli-konsol.log")
            Start-Process -WindowStyle Hidden -FilePath "cmd.exe" -ArgumentList "/s", "/c", "`"$k`"" | Out-Null
            Yaz "canli (go2rtc) çalışmıyordu — başlatıldı"
        }
    }

    foreach ($s in $servisler) {
        if ($bekle[$s.Ad] -and (Get-Date) -lt $bekle[$s.Ad]) { continue }
        if (SurecVarMi $s.Modul) { $hata[$s.Ad] = 0; continue }

        Baslat $s
        Start-Sleep -Seconds 5
        if (SurecVarMi $s.Modul) {
            Yaz "$($s.Ad) çalışmıyordu — başlatıldı"
            $hata[$s.Ad] = 0
        } else {
            $hata[$s.Ad] = [int]$hata[$s.Ad] + 1
            Yaz "$($s.Ad) başlatılamadı (üst üste $($hata[$s.Ad])) — bkz $($s.Log)"
            if ($hata[$s.Ad] -ge 5) {
                $bekle[$s.Ad] = (Get-Date).AddMinutes(10)
                Yaz "$($s.Ad) 10 dakika beklemeye alındı (yeniden başlatma fırtınası koruması)"
                $hata[$s.Ad] = 0
            }
        }
    }
    Start-Sleep -Seconds $Aralik
}
