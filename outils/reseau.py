"""Accès à distance (téléphones, iPads) : qui a le droit de se connecter, et à quelle adresse.

Principe : sans comptes, la porte d'entrée est le réseau privé Tailscale (gratuit, chiffré, sans port ouvert sur le routeur).
Seuls les appareils que tu as invités dans ton Tailscale ont une adresse 100.64.x.x - 100.127.x.x. En mode « réseau »,
le programme n'accepte donc que :
  - cet ordinateur lui-même (127.0.0.1) ;
  - les appareils de ton Tailscale (adresses 100.64.0.0/10).
Toute autre machine (Wi-Fi de l'atelier, Internet) est refusée, même si elle atteint le port.

Accès en HTTPS (nécessaire pour le bouton Partager de l'iPhone) : « tailscale serve » relaie https://pc.mon-reseau.ts.net vers ce
programme. Voir relais_tailscale() : une requête relayée est traitée comme venant d'un appareil Tailscale, jamais de cet ordinateur.
"""
import ipaddress
import shutil
import socket
import subprocess
from pathlib import Path

TAILSCALE = ipaddress.ip_network("100.64.0.0/10")
TAILSCALE_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
EN_TETES_RELAIS = ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "Tailscale-User-Login")
ADRESSE_RELAIS_INCONNUE = "100.64.0.0"      # relais sans adresse lisible : une adresse Tailscale neutre (jamais « cet ordinateur »)
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


def _nom_ts_net(valeur):
    """« pc.mon-reseau.ts.net » (ou avec « :443 ») -> le nom ; None pour tout autre hôte."""
    if not valeur or valeur.startswith("["):
        return None
    nom, _, port = valeur.lower().partition(":")
    return nom if nom.endswith(".ts.net") and len(nom) > 7 and port in ("", "443") else None


def relais_tailscale(en_tetes, adresse_client, port):
    """La requête passe-t-elle par « tailscale serve » (accès en HTTPS : https://pc.mon-reseau.ts.net) ?

    « tailscale serve » tourne sur cet ordinateur et relaie vers 127.0.0.1 : la requête ARRIVE donc de 127.0.0.1, mais elle vient
    en réalité d'un téléphone. Il ne faut surtout pas la prendre pour « cet ordinateur » (qui n'a pas besoin de se connecter).

    Retourne :
      None   : requête directe (pas de relais) ;
      False  : relais suspect (hôte qui n'est pas un nom *.ts.net) : à refuser ;
      dict   : relais reconnu : {"ip": adresse Tailscale de l'appareil (ou adresse neutre), "https": bool,
               "hote": nom *.ts.net, ou None si le relais ne l'a pas transmis}.
    Seule une requête arrivant de 127.0.0.1 peut être un relais : les mêmes en-têtes envoyés par un autre appareil sont ignorés.
    """
    ip = _ip(adresse_client)
    if ip is None or not ip.is_loopback:
        return None
    hote = en_tetes.get("Host") or ""
    signale = any(en_tetes.get(e) for e in EN_TETES_RELAIS)
    nom = _nom_ts_net(hote)                                   # « pc.mon-reseau.ts.net », sans le port du programme : l'adresse HTTPS
    if not signale and nom is None:
        return None                                           # accès direct : les règles habituelles (hote_autorise) s'appliquent
    if nom is None:
        separe = _separer_hote(hote)
        if not (separe is not None and separe[0] in LOCAL and separe[1] == str(port)):
            return False                                      # relais annoncé pour un hôte qui n'est ni un nom *.ts.net ni cet ordinateur
        transmis = en_tetes.get("X-Forwarded-Host") or ""
        nom = _nom_ts_net(transmis)
        if transmis and nom is None:
            return False
    appareil = ADRESSE_RELAIS_INCONNUE
    for morceau in reversed((en_tetes.get("X-Forwarded-For") or "").split(",")):      # le dernier est celui ajouté par le relais
        a = _ip(morceau.strip())
        if a is not None and ((a.version == 4 and a in TAILSCALE) or (a.version == 6 and a in TAILSCALE_V6)):
            appareil = str(a)
            break
    return {"ip": appareil, "https": (en_tetes.get("X-Forwarded-Proto") or "").lower() == "https", "hote": nom}


def origine_relais_ok(origine, relais):
    """En-tête « Origin » d'une requête relayée : le même nom *.ts.net que l'hôte (ou, s'il n'a pas été transmis, un nom *.ts.net)."""
    nom = _nom_ts_net(origine)
    return nom is not None and (relais["hote"] is None or nom == relais["hote"])


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
