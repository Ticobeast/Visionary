@echo off
rem Double-clic : restaurer une sauvegarde (ferme d'abord le programme).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py restaurer_sauvegarde.py) else (python restaurer_sauvegarde.py)
pause
