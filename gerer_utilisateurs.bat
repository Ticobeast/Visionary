@echo off
rem Double-clic : gerer les comptes de l'equipe (ajouter, changer un mot de passe, desactiver).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py gerer_utilisateurs.py) else (python gerer_utilisateurs.py)
pause
