@echo off
title Excel AI - New PC Setup
cd /d "%~dp0"
echo =====================================================================
echo    EXCEL AI - NEW PC SETUP WIZARD
echo =====================================================================
echo.
echo [1/3] Installing Python dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies. Please ensure Python is installed and added to PATH.
    pause
    exit /b %errorlevel%
)
echo Python packages installed successfully!
echo.
echo [2/3] Checking environment file (.env)...
if not exist ".env" (
    echo [.env not found]: Creating template from .env.example...
    copy .env.example .env >nul
    echo [IMPORTANT] Please open the newly created .env file and paste your API keys!
) else (
    echo [.env found]: Configuration is ready!
)
echo.
echo [3/3] Setting up Mobile App dependencies (if Node.js is present)...
where node >nul 2>nul
if %errorlevel% equ 0 (
    if exist "excel-ai-mobile\package.json" (
        echo Node.js found! Installing mobile app dependencies...
        cd excel-ai-mobile
        call npm install
        cd ..
        echo Mobile dependencies installed successfully!
    )
) else (
    echo Note: Node.js is not detected. Web backend and PDF ingestion will work normally.
    echo If you wish to run the mobile app locally, install Node.js from https://nodejs.org
)
echo.
echo =====================================================================
echo    SETUP COMPLETE!
echo =====================================================================
echo To run local web app:             run_web_local.bat
echo To run mobile app (Expo):         run_mobile_app.bat
echo To batch-upload study materials:  upload_zip.bat
echo =====================================================================
echo.
pause
