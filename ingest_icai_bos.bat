@echo off
title Excel AI - Official ICAI BoS Study Material Harvester
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo =====================================================================
echo    🎓 EXCEL AI COACH - OFFICIAL ICAI BoS KNOWLEDGE HARVESTER
echo =====================================================================
echo    Automates crawling ICAI BoS portal, downloading all chapter PDFs,
echo    and indexing them directly into Pinecone Cloud with Level Namespaces.
echo =====================================================================
echo.
echo Select the ICAI syllabus to crawl and ingest into Pinecone Cloud:
echo [1] CA Foundation (English) - May 2026 (4 Papers)
echo [2] CA Foundation (Hindi)   - 2026 (4 Papers)
echo [3] CA Intermediate (English) - May 2026 (8 Papers)
echo [4] CA Intermediate (Hindi)   - May 2026 (8 Papers)
echo [5] CA Final (English) - May 2026 (5 Papers)
echo [6] CA Final (Hindi)   - May 2026 (5 Papers)
echo [7] Harvest ALL (Foundation + Inter + Final, English ^& Hindi)
echo [8] Enter custom ICAI BoS URL
echo.
set /p "CHOICE=Enter choice [1-8, default is 1]: "
if "%CHOICE%"=="" set "CHOICE=1"

if "%CHOICE%"=="8" (
    set /p "CUSTOM_URL=Paste ICAI BoS webpage URL: "
    set /p "COURSE=Course (CA/CS/CMA) [default: CA]: "
    if "%COURSE%"=="" set "COURSE=CA"
    set /p "LEVEL=Level (Foundation/Inter/Final) [default: Foundation]: "
    if "%LEVEL%"=="" set "LEVEL=Foundation"
    set /p "LANG=Language (English/Hindi) [default: English]: "
    if "%LANG%"=="" set "LANG=English"
    python scripts/ingest_icai_bos.py --url "%CUSTOM_URL%" --course "%COURSE%" --level "%LEVEL%" --language "%LANG%"
) else if "%CHOICE%"=="7" (
    python scripts/ingest_icai_bos.py --preset all
) else (
    python scripts/ingest_icai_bos.py --preset %CHOICE%
)

echo.
echo Press any key to exit...
pause >nul
