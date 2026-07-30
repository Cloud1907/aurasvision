; AurasVision — Windows kurulum sihirbazı (NSIS)
;
; Üretim (Linux'ta):  makensis windows/installer.nsi
; Çıktı:              windows/AurasVision-Kurulum.exe
;
; Kullanıcı .exe'ye çift tıklar; sihirbaz uygulamayı kopyalar, ORTAMI kurar
; (Python + Docker Desktop, winget ile), bağımlılıkları yükler, erişim anahtarı
; üretir, kısayolları ve kaldırma programını oluşturur.

Unicode true
Name "AurasVision"
OutFile "AurasVision-Kurulum.exe"
InstallDir "$PROGRAMFILES64\AurasVision"
InstallDirRegKey HKLM "Software\AurasVision" "InstallDir"
RequestExecutionLevel admin       ; Program Files'a yazma + servis görevi için
ShowInstDetails show
SetCompressor /SOLID lzma

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_WELCOMEPAGE_TITLE "AurasVision Kurulumu"
!define MUI_WELCOMEPAGE_TEXT "Bu sihirbaz AurasVision görüntü analitiği platformunu kurar.$\r$\n$\r$\nKurulum sırasında gerekli ortam bileşenleri (Python ve Docker Desktop) eksikse otomatik olarak indirilip kurulur. Bu nedenle internet bağlantısı gereklidir ve kurulum birkaç dakika sürebilir.$\r$\n$\r$\nDevam etmek için İleri'ye tıklayın."
!define MUI_FINISHPAGE_TITLE "Kurulum tamamlandı"
!define MUI_FINISHPAGE_TEXT "AurasVision kuruldu.$\r$\n$\r$\nErişim anahtarınız kurulum klasöründeki ERISIM-ANAHTARI.txt dosyasındadır — panele ilk girişte sorulur.$\r$\n$\r$\nMasaüstündeki AurasVision kısayolu paneli başlatır."
!define MUI_FINISHPAGE_RUN "$INSTDIR\windows\AurasVision-Baslat.bat"
!define MUI_FINISHPAGE_RUN_TEXT "AurasVision'ı şimdi başlat"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\ERISIM-ANAHTARI.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Erişim anahtarını göster"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Turkish"

Section "AurasVision" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"

  DetailPrint "Uygulama dosyaları kopyalanıyor..."
  File /r /x .venv /x .git /x output /x node_modules /x __pycache__ /x .pytest_cache \
       /x allure-results /x test-results /x playwright-report /x data \
       "..\src"
  File /r "..\web"
  File /r "..\db"
  File /r "..\deploy"
  File /r /x __pycache__ "..\scripts"
  File /r "..\windows"
  File "..\config.yaml"
  File "..\requirements.txt"
  File "..\docker-compose.yml"
  File "..\README.md"
  File /nonfatal "..\yolo11n.pt"
  SetOutPath "$INSTDIR\go2rtc"
  File /nonfatal "..\go2rtc\*.yaml"
  SetOutPath "$INSTDIR\data\videos"
  SetOutPath "$INSTDIR"

  DetailPrint ""
  DetailPrint "Ortam kuruluyor (Python, Docker, bağımlılıklar)..."
  DetailPrint "Bu adım birkaç dakika sürebilir, lütfen bekleyin."
  nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\windows\setup.ps1" -NoLaunch'
  Pop $0
  ${If} $0 != 0
    DetailPrint ""
    DetailPrint "UYARI: ortam kurulumu tamamlanamadı (kod: $0)."
    DetailPrint "Uygulama dosyaları kuruldu. Kurulum klasöründeki"
    DetailPrint "windows\AurasVision-Kurulum.bat dosyasını yönetici olarak çalıştırıp tekrar deneyin."
  ${EndIf}

  ; Kısayollar
  CreateDirectory "$SMPROGRAMS\AurasVision"
  CreateShortcut "$SMPROGRAMS\AurasVision\AurasVision.lnk" "$INSTDIR\windows\AurasVision-Baslat.bat" "" "" 0 SW_SHOWMINIMIZED
  CreateShortcut "$SMPROGRAMS\AurasVision\AurasVision Durdur.lnk" "$INSTDIR\windows\AurasVision-Durdur.bat" "" "" 0 SW_SHOWMINIMIZED
  CreateShortcut "$SMPROGRAMS\AurasVision\Kaldır.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\AurasVision.lnk" "$INSTDIR\windows\AurasVision-Baslat.bat" "" "" 0 SW_SHOWMINIMIZED

  ; Kayıt defteri + kaldırma programı (Windows "Uygulamalar" listesinde görünür)
  WriteRegStr HKLM "Software\AurasVision" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AurasVision" \
                   "DisplayName" "AurasVision — Görüntü Analitiği"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AurasVision" \
                   "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AurasVision" \
                   "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AurasVision" \
                   "Publisher" "AurasVision"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AurasVision" \
                   "NoModify" 1
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  ; Servis görevi ve çalışan süreçler önce durdurulur
  nsExec::ExecToLog 'schtasks /Delete /TN "AurasVision" /F'
  nsExec::ExecToLog 'taskkill /F /IM python.exe /FI "WINDOWTITLE eq AurasVision*"'

  Delete "$DESKTOP\AurasVision.lnk"
  RMDir /r "$SMPROGRAMS\AurasVision"

  ; KAYITLAR VE VERİTABANI SİLİNMEZ — kamera kaydı mevzuat gereği saklanır,
  ; kaldırma işlemi delil niteliğindeki arşivi yok etmemeli. Kullanıcı isterse
  ; output klasörünü kendisi siler.
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\src"
  RMDir /r "$INSTDIR\web"
  RMDir /r "$INSTDIR\db"
  RMDir /r "$INSTDIR\deploy"
  RMDir /r "$INSTDIR\scripts"
  RMDir /r "$INSTDIR\windows"
  RMDir /r "$INSTDIR\.venv"
  Delete "$INSTDIR\config.yaml"
  Delete "$INSTDIR\requirements.txt"
  Delete "$INSTDIR\docker-compose.yml"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\*.pt"
  RMDir "$INSTDIR"          ; yalnız boşsa siler — output/ ve .env kalır

  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AurasVision"
  DeleteRegKey HKLM "Software\AurasVision"

  MessageBox MB_OK "AurasVision kaldırıldı.$\r$\n$\r$\nKamera kayıtları ve veritabanı korundu:$\r$\n$INSTDIR\output$\r$\n$\r$\nBunlara ihtiyacınız yoksa klasörü elle silebilirsiniz."
SectionEnd
