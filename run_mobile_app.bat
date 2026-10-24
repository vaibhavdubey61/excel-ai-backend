@echo off
title Excel AI Mobile App (Expo Go)
cd /d "%~dp0excel-ai-mobile"
if exist "C:\Users\lenovo\AppData\Local\Programs\node-lts" (
    set "PATH=C:\Users\lenovo\AppData\Local\Programs\node-lts;%PATH%"
)
echo =====================================================================
echo    EXCEL AI MOBILE APP - EXCEL EDUCATIONAL INSTITUTE
echo =====================================================================
echo    1. Install "Expo Go" app from Google Play Store or Apple App Store.
echo    2. Scan the QR code below using Expo Go (or your phone camera).
echo    3. The app will launch directly on your phone!
echo =====================================================================
echo.
npx expo start
pause
