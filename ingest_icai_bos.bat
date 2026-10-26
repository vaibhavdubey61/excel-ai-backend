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
echo Select the ICAI syllabus to crawl and ingest:
echo [1] CA Foundation (May 2026 Scheme - 4 Papers, 18 Chapters)
echo [2] Enter custom ICAI BoS URL
echo.
set /p "CHOICE=Enter choice [1 or 2, default is 1]: "

if "%CHOICE%"=="2" (
    set /p "CUSTOM_URL=Paste ICAI BoS webpage URL: "
    set /p "COURSE=Course (CA/CS/CMA) [default: CA]: "
    if "%COURSE%"=="" set "COURSE=CA"
    set /p "LEVEL=Level (Foundation/Inter/Final) [default: Foundation]: "
    if "%LEVEL%"=="" set "LEVEL=Foundation"
    python scripts/ingest_icai_bos.py --url "%CUSTOM_URL%" --course "%COURSE%" --level "%LEVEL%"
) else (
    python scripts/ingest_icai_bos.py --course CA --level Foundation
)

echo.
echo Press any key to exit...
pause >nul
