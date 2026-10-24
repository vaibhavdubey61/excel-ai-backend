@echo off
setlocal enabledelayedexpansion
title Excel AI - Batch Study Material Ingester
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo =====================================================================
echo    EXCEL AI - 1-CLICK STUDY MATERIALS BATCH INGESTER
echo =====================================================================
echo    Extracts PDFs, generates AI embeddings, and indexes to Pinecone.
echo =====================================================================
echo.

if not "%~1"=="" (
    python ingest_materials.py "%~1"
) else (
    echo [1] Press ENTER to ingest all PDFs in "study_materials\" folder
    echo [2] Or drag and drop any .ZIP file or PDF folder here and press Enter:
    set "TARGET_PATH="
    set /p "TARGET_PATH=Choice / Path: "
    if "!TARGET_PATH!"=="" (
        python ingest_materials.py "study_materials"
    ) else (
        python ingest_materials.py "!TARGET_PATH!"
    )
)

echo.
echo Press any key to exit...
pause >nul
