@echo off
title AurasVision Durdur
taskkill /F /IM python.exe /FI "WINDOWTITLE eq AurasVision*" >nul 2>&1
taskkill /F /IM go2rtc.exe >nul 2>&1
echo AurasVision durduruldu.
timeout /t 3 >nul
