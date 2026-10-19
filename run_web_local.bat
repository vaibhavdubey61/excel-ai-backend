@echo off
title Excel AI Web Server (Local)
cd /d "%~dp0"
echo =====================================================================
echo    EXCEL AI LOCAL SERVER - EXCEL EDUCATIONAL INSTITUTE
echo =====================================================================
echo    Starting local web server at http://localhost:8000
echo    - Student Chat App:   http://localhost:8000/
echo    - Study Materials:    http://localhost:8000/admin
echo =====================================================================
echo.
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
pause
