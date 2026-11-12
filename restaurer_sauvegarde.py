"""Restaurer une sauvegarde de la VRAIE base (ferme d'abord le programme).

Fonctionne avec le bouton « Exécuter » de VS Code, un double-clic sur restaurer_sauvegarde.bat, ou : python restaurer_sauvegarde.py
Pour la base d'essai :  python restaurer_sauvegarde.py --essai
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
import sauvegardes  # noqa: E402
from noyau import DB_DEFAUT  # noqa: E402

db = DB_DEFAUT.parent / "test.db" if "--essai" in sys.argv else DB_DEFAUT
sys.exit(sauvegardes.main(db))
