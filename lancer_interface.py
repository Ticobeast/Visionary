"""Ouvre l'interface sur la VRAIE base (data/sylvainculteur.db).

Fonctionne avec le bouton « Exécuter » de VS Code, un double-clic, ou : python lancer_interface.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
import interface  # noqa: E402

interface.main([])
