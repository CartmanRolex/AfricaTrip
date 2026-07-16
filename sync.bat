@echo off
rem Met a jour le site (Google Sheet + photos Drive) et publie sur GitHub Pages.
cd /d "%~dp0"
python src\sync.py
echo.
pause
