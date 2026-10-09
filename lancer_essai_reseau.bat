@echo off
rem Double-clic : base d'ESSAI (fausses donnees) avec acces a distance (telephones, iPads) par Tailscale.
rem Un compte temporaire "essai" est cree dans la base d'essai ; son mot de passe s'affiche dans cette fenetre.
rem Laisser cette fenetre ouverte, et l'ordinateur allume (mise en veille desactivee).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py outils\interface.py --essai --reseau) else (python outils\interface.py --essai --reseau)
pause
