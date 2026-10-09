"""Ouvre l'interface sur la base d'ESSAI (fausses données) avec l'accès à distance : pour essayer sur un téléphone ou un iPad.

Un compte administrateur temporaire « essai » est créé dans la base d'essai (le nom et le mot de passe s'affichent au démarrage).
Fonctionne avec le bouton « Exécuter » de VS Code, un double-clic, ou : python lancer_essai_reseau.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
import interface  # noqa: E402

interface.main(["--essai", "--reseau"])
