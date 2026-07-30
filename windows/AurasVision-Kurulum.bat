@echo off
REM AurasVision — Windows kurulumu. Kullanici bu dosyaya CIFT TIKLAR, baska hicbir sey yapmaz.
REM Yonetici yetkisi gerekiyorsa kendini yeniden baslatir.
title AurasVision Kurulum

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Yonetici yetkisi isteniyor...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if %errorlevel% neq 0 (
    echo.
    echo Kurulum tamamlanamadi. Yukaridaki mesaji ekip ile paylasin.
    pause
    exit /b 1
)
pause
