@echo off
rem AurasVision baslatici — pakete STATIK girer: kurulum betigi hic kosmasa
rem bile masaustu kisayolunun hedefi var olur. setup.ps1 kurulum sirasinda
rem bu dosyayi profile ozel surumuyle (token'li adres vb.) uzerine yazar.
title AurasVision
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  AurasVision kurulumu tamamlanmamis gorunuyor: Python ortami eksik.
  echo  Kurulumu tekrar calistirin:
  echo    windows\AurasVision-Kurulum.bat  ^(sag tik - Yonetici olarak calistir^)
  echo  Hata ayrintisi icin kurulum klasorundeki kurulum-log.txt dosyasina bakin.
  echo.
  pause
  exit /b 1
)
if not exist output\logs mkdir output\logs
if not exist go2rtc\go2rtc.yaml (mkdir go2rtc 2>nul & type nul > go2rtc\go2rtc.yaml)
if exist bin\go2rtc.exe start "AurasVision Canli" /min cmd /c "bin\go2rtc.exe -config go2rtc\go2rtc.yaml 1>>output\logs\canli-konsol.log 2>&1"
start "" http://127.0.0.1:8000
start "AurasVision Sunucu" /min cmd /c ".venv\Scripts\python.exe -m src.server 1>>output\logs\sunucu-konsol.log 2>&1"
timeout /t 3 >nul
start "AurasVision Kayit" /min cmd /c ".venv\Scripts\python.exe -m src.recorder 1>>output\logs\kayit-konsol.log 2>&1"
start "AurasVision Analiz" /min cmd /c ".venv\Scripts\python.exe -m src.worker 1>>output\logs\analiz-konsol.log 2>&1"
echo AurasVision calisiyor. Panel: http://127.0.0.1:8000
echo Erisim anahtari kurulum klasorundeki ERISIM-ANAHTARI.txt dosyasindadir.
timeout /t 5 >nul
