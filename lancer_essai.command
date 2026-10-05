#!/bin/bash
# Double-clic (Mac) : ouvre l'interface sur la base d'ESSAI (fausses données, créée au besoin).
cd "$(dirname "$0")"
python3 outils/interface.py --essai
