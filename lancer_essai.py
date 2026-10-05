"""Ouvre l'interface sur la base d'ESSAI (fausses données, créée au besoin).

Fonctionne avec le bouton « Exécuter » de VS Code, un double-clic, ou : python lancer_essai.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
import interface  # noqa: E402

interface.main(["--essai"])
