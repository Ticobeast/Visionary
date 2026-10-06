"""Ouvre l'interface sur la VRAIE base, avec l'accès à distance (téléphones, iPads) par ton réseau privé Tailscale.

Voir docs/acces_a_distance.md. Fonctionne avec le bouton « Exécuter » de VS Code, un double-clic, ou : python lancer_reseau.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
import interface  # noqa: E402

interface.main(["--reseau"])
