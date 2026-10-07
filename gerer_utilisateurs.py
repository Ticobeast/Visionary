"""Gérer les comptes de l'équipe (ajouter, changer un mot de passe, désactiver) sur la VRAIE base.

Fonctionne avec le bouton « Exécuter » de VS Code, un double-clic sur gerer_utilisateurs.bat, ou : python gerer_utilisateurs.py
Pour la base d'essai :  python gerer_utilisateurs.py --essai
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
import auth  # noqa: E402
from noyau import DB_DEFAUT  # noqa: E402

db = DB_DEFAUT.parent / "test.db" if "--essai" in sys.argv else DB_DEFAUT
sys.exit(auth.main(db))
