@echo off
REM AurasVision gözcüsü — servisleri baþlatýr ve ayakta tutar.
REM Açýlýþta bu çalýþýr; ayrýca elle çift týklanabilir (ikinci kopya açýlmaz).
title AurasVision Gozcu
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0AurasVision-Gozcu.ps1"
