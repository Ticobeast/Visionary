@echo off
rem Double-clic : ouvre l'interface sur la base d'ESSAI (fausses données, créée au besoin).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py outils\interface.py --essai) else (python outils\interface.py --essai)
pause
