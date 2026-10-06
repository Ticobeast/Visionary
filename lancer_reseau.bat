@echo off
rem Double-clic : interface SylvainCulteur avec acces a distance (telephones, iPads) par Tailscale.
rem Laisser cette fenetre ouverte, et l'ordinateur allume (mise en veille desactivee).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py outils\interface.py --reseau) else (python outils\interface.py --reseau)
pause
