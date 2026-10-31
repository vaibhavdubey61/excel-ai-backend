@echo off
echo Starting OpsPulse Client Operations Dashboard...
echo Open your browser at http://localhost:3300
start http://localhost:3300
python -m http.server 3300
pause
