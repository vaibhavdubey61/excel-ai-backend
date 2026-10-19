@echo off
title Excel AI - Batch Study Material Ingester
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo =====================================================================
echo    EXCEL AI - 1-CLICK STUDY MATERIALS BATCH INGESTER
echo =====================================================================
echo    This tool unpacks your ZIP file, extracts all coaching PDFs,
echo    generates AI vector embeddings, and stores them in Pinecone Cloud.
echo =====================================================================
echo.

if "%~1"=="" (
    echo Drag and drop your .zip file onto this window and press Enter:
    set /p "ZIP_PATH=ZIP file path: "
) else (
    set "ZIP_PATH=%~1"
)

python ingest_materials.py "%ZIP_PATH%"

echo.
echo Press any key to exit...
pause >nul
