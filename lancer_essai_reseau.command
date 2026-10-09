#!/bin/bash
# Double-clic (Mac) : base d'ESSAI (fausses données) avec accès à distance (téléphones, iPads) par Tailscale.
# Un compte temporaire « essai » est créé dans la base d'essai ; son mot de passe s'affiche dans cette fenêtre.
cd "$(dirname "$0")"
python3 outils/interface.py --essai --reseau
