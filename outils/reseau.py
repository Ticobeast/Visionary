"""Accès à distance (téléphones, iPads) : qui a le droit de se connecter, et à quelle adresse.

Principe : sans comptes, la porte d'entrée est le réseau privé Tailscale (gratuit, chiffré, sans port ouvert sur le routeur).
Seuls les appareils que tu as invités dans ton Tailscale ont une adresse 100.64.x.x - 100.127.x.x. En mode « réseau »,
le programme n'accepte donc que :
  - cet ordinateur lui-même (127.0.0.1) ;
  - les appareils de ton Tailscale (adresses 100.64.0.0/10).
Toute autre machine (Wi-Fi de l'atelier, Internet) est refusée, même si elle atteint le port.
"""
import ipaddress
import shutil
import socket
import subprocess
from pathlib import Path

TAILSCALE = ipaddress.ip_network("100.64.0.0/10")
LOCAL = ("localhost", "127.0.0.1")
CHEMINS_TAILSCALE_WINDOWS = (r"C:\Program Files\Tailscale\tailscale.exe", r"C:\Program Files (x86)\Tailscale\tailscale.exe")


def _ip(texte):
    try:
        return ipaddress.ip_address(texte)
    except ValueError:
        return None


def client_autorise(adresse, reseau):
    """Adresse IP de l'appareil qui se connecte : toujours cet ordinateur ; en mode réseau, aussi les appareils Tailscale."""
    ip = _ip(adresse)
    if ip is None:
        return False
    if ip.is_loopback:
        return True
    return bool(reseau) and ip.version == 4 and ip in TAILSCALE


def _separer_hote(valeur):
    """« nom:8765 » -> (« nom », « 8765 ») ; None si le format est étrange."""
    if not valeur or valeur.startswith("["):
        return None
    nom, deux_points, port = valeur.rpartition(":")
    if not deux_points or not port.isdigit():
        return None
    return nom.lower(), port


def hote_autorise(valeur, port, reseau, nom_machine=None):
    """En-tête « Host » : protège contre les sites web qui se feraient passer pour ton application (DNS rebinding).

    Toujours permis : localhost et 127.0.0.1. En mode réseau : une adresse Tailscale (100.x.x.x), un nom *.ts.net
    (MagicDNS) ou le nom de cet ordinateur. Le numéro de port doit être celui du serveur.
    """
    separe = _separer_hote(valeur)
    if separe is None or separe[1] != str(port):
        return False
    nom = separe[0]
    if nom in LOCAL:
        return True
    if not reseau:
        return False
    ip = _ip(nom)
    if ip is not None:
        return ip.version == 4 and ip in TAILSCALE
    machine = (nom_machine if nom_machine is not None else socket.gethostname()).lower()
    return nom.endswith(".ts.net") or nom == machine or nom == machine.split(".")[0]


def adresses_tailscale():
    """Adresses Tailscale IPv4 de cet ordinateur (via la commande tailscale, si installée), sinon liste vide."""
    exe = shutil.which("tailscale") or next((c for c in CHEMINS_TAILSCALE_WINDOWS if Path(c).exists()), None)
    if not exe:
        return []
    try:
        sortie = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [l.strip() for l in sortie.splitlines() if _ip(l.strip()) is not None and _ip(l.strip()) in TAILSCALE]
