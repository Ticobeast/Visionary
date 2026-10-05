@echo off
rem Double-clic : ouvre l'interface de saisie SylvainCulteur dans le navigateur.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py outils\interface.py) else (python outils\interface.py)
pause
