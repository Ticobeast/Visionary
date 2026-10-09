"""Photos d'une soumission ou d'un chantier : prises avec le téléphone, choisies dans la galerie, ou ajoutées depuis l'ordinateur.

Où elles vont : dans le dossier de photos de la fiche (`dossier_photos`, voir « Paramètres avancés ») ; s'il est vide, dans
`data/photos/chantier-N`. Rien n'est écrit dans la base : les photos sont de simples fichiers (JPEG ou PNG) que tu peux aussi
glisser toi-même dans ce dossier. Elles apparaissent en vignettes dans la fiche et dans le PDF de la journée.

Comment : le navigateur réduit chaque photo (1 600 px, JPEG léger : quelques centaines de Ko au lieu de 5 Mo) et en fait une
vignette, puis envoie les octets tels quels (le corps de la requête EST l'image). Le serveur ne fait confiance à rien :
il reconnaît le format par les premiers octets (pas par le nom ou le type annoncé), limite la taille et le nombre de photos,
invente lui-même le nom du fichier et ne sort jamais du dossier de données.

    GET  /chantier/12/photos/NOM            la photo ; ?v=1 : sa vignette (ou la photo si elle n'a pas de vignette)
    POST /chantier/12/photos                ajoute une photo (corps = JPEG ou PNG) ; répond {"nom": "..."}
    POST /chantier/12/photos/NOM/vignette   range la vignette de cette photo (JPEG léger)
    POST /chantier/12/photos/NOM/supprimer  efface la photo et sa vignette
(« soumission » et « chantier » sont interchangeables : c'est la même fiche.)
"""
import datetime
import json
import re
import secrets
from pathlib import Path

from vue import _BASE, esc, gabarit, redirection, url_fiche

TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
LIMITE_OCTETS = 20_000_000          # une photo plus lourde est refusée (le navigateur la réduit avant l'envoi)
LIMITE_VIGNETTE = 400_000
MAX_PHOTOS = 80                     # par fiche
NOM_SUR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
VIGNETTES = ".vignettes"


def format_de(octets):
    """« .jpg » ou « .png » d'après les premiers octets, sinon None."""
    if octets[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if octets[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    return None


def _json(statut, **donnees):
    return statut, [("Content-Type", "application/json; charset=utf-8")], json.dumps(donnees, ensure_ascii=False).encode("utf-8")


def dossier_de(conn, chantier_id):
    """(dossier absolu, genre) de la fiche, ou (None, None) si la fiche n'existe pas ou si le dossier sortirait de data/."""
    r = conn.execute("SELECT dossier_photos, genre FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    if r is None or not _BASE.get("db"):
        return None, None
    base = Path(_BASE["db"]).resolve().parent
    dossier = (base / (r[0] or f"photos/chantier-{chantier_id}")).resolve()
    try:
        dossier.relative_to(base)
    except ValueError:
        return None, None
    return dossier, r[1]


def lister(dossier):
    """Noms des photos du dossier, dans l'ordre de prise (les noms commencent par la date)."""
    if dossier is None or not dossier.is_dir():
        return []
    return sorted((p.name for p in dossier.iterdir() if p.is_file() and p.suffix.lower() in TYPES), key=str.lower)


# ---------------------------------------------------------------------------
# La carte « Photos » de la fiche
# ---------------------------------------------------------------------------
SCRIPT = r"""<script>(function(){
var c=document.currentScript.parentNode,base=c.getAttribute("data-base"),etat=c.querySelector(".photo-etat"),v=c.querySelector(".visionneuse");
function redim(f,max,q){return new Promise(function(ok,ko){var u=URL.createObjectURL(f),i=new Image();
i.onload=function(){var r=Math.min(1,max/Math.max(i.naturalWidth,i.naturalHeight)),w=Math.round(i.naturalWidth*r),h=Math.round(i.naturalHeight*r),k=document.createElement("canvas");
k.width=w;k.height=h;k.getContext("2d").drawImage(i,0,0,w,h);URL.revokeObjectURL(u);k.toBlob(function(b){b?ok(b):ko();},"image/jpeg",q);};
i.onerror=function(){URL.revokeObjectURL(u);ko();};i.src=u;});}
function envoyer(url,b){return fetch(url,{method:"POST",headers:{"Content-Type":b.type||"image/jpeg"},body:b,credentials:"same-origin"}).then(function(r){
return r.json().catch(function(){return {};}).then(function(j){if(!r.ok){throw new Error(j.erreur||("erreur "+r.status));}return j;});});}
async function traiter(fichiers){var n=fichiers.length,i,f,g,p,t;
try{for(i=0;i<n;i++){f=fichiers[i];etat.textContent="Envoi de la photo "+(i+1)+" sur "+n+"…";
try{g=await redim(f,1600,0.82);}catch(e){g=f;}
p=await envoyer(base,g);
try{t=await redim(f,360,0.7);await envoyer(base+"/"+p.nom+"/vignette",t);}catch(e){}}
etat.textContent="Terminé.";try{sessionStorage.setItem("pos:"+location.pathname,String(window.pageYOffset));}catch(e){}location.reload();}
catch(e){etat.textContent="Échec de l'envoi : "+e.message;}}
c.querySelectorAll("input[type=file]").forEach(function(inp){inp.addEventListener("change",function(){if(inp.files.length){traiter(Array.prototype.slice.call(inp.files));}inp.value="";});});
c.querySelectorAll("a.photo").forEach(function(a){a.addEventListener("click",function(e){e.preventDefault();v.querySelector("img").src=a.href;
v.querySelector("form").action=base+"/"+a.getAttribute("data-nom")+"/supprimer";v.hidden=false;});});
v.querySelector("[data-fermer]").addEventListener("click",function(){v.hidden=true;v.querySelector("img").removeAttribute("src");});
})();</script>"""


def bloc(conn, chantier_id):
    """La carte « Photos » : vignettes, boutons pour en ajouter, visionneuse (toucher une photo l'agrandit ; on peut la supprimer)."""
    dossier, genre = dossier_de(conn, chantier_id)
    if dossier is None:
        return ""
    base = f"{url_fiche(chantier_id, genre)}/photos"
    noms = lister(dossier)
    vignettes = "".join(f'<a class="photo" href="{base}/{esc(n)}" data-nom="{esc(n)}"><img src="{base}/{esc(n)}?v=1" alt="Photo" loading="lazy"></a>' for n in noms)
    corps = (f'<div class="photos-grille">{vignettes}</div>' if noms
             else '<p class="doux photos-vide">Aucune photo. Prends-en avec le téléphone, ou ajoute-en depuis la galerie ou l\'ordinateur.</p>')
    return (f'<div class="carte photos" id="photos" data-base="{base}"><h2>Photos{f" ({len(noms)})" if noms else ""}</h2>{corps}'
            '<div class="barre photos-actions">'
            '<label class="bouton photo-prendre">Prendre une photo<input type="file" accept="image/*" capture="environment" hidden></label>'
            '<label class="bouton secondaire">Ajouter des photos<input type="file" accept="image/*" multiple hidden></label></div>'
            '<p class="doux photo-etat" aria-live="polite"></p>'
            '<div class="visionneuse" hidden><img alt="Photo agrandie"><div class="barre">'
            '<button type="button" class="secondaire" data-fermer>Fermer</button>'
            '<form method="post" action="" onsubmit="return confirm(\'Supprimer cette photo ?\')"><button type="submit" class="danger">Supprimer</button></form></div></div>'
            + SCRIPT + "</div>")


# ---------------------------------------------------------------------------
# Les adresses
# ---------------------------------------------------------------------------
def _nom_valide(nom):
    return bool(NOM_SUR.match(nom)) and Path(nom).suffix.lower() in TYPES


def voir(conn, query, chantier_id, nom):
    dossier, _ = dossier_de(conn, chantier_id)
    if dossier is None or not _nom_valide(nom):
        return _json("404 Not Found", erreur="photo introuvable")
    fichier = dossier / nom
    if query.get("v") == "1" and (dossier / VIGNETTES / (nom + ".jpg")).is_file():
        fichier = dossier / VIGNETTES / (nom + ".jpg")
    if not fichier.is_file():
        return _json("404 Not Found", erreur="photo introuvable")
    octets = fichier.read_bytes()
    type_ = TYPES.get(format_de(octets) or "", "")
    if not type_:
        return _json("404 Not Found", erreur="photo illisible")
    return "200 OK", [("Content-Type", type_), ("Cache-Control", "private, max-age=3600"), ("X-Content-Type-Options", "nosniff")], octets


def ajouter(conn, query, form, chantier_id):
    dossier, _ = dossier_de(conn, chantier_id)
    if dossier is None:
        return _json("404 Not Found", erreur="fiche introuvable")
    octets = form.get("_octets")
    if not octets:
        return _json("400 Bad Request", erreur="aucune image reçue")
    if len(octets) > LIMITE_OCTETS:
        return _json("413 Payload Too Large", erreur="photo trop lourde")
    extension = format_de(octets)
    if extension is None:
        return _json("415 Unsupported Media Type", erreur="seuls les JPEG et les PNG sont acceptés")
    if len(lister(dossier)) >= MAX_PHOTOS:
        return _json("409 Conflict", erreur=f"{MAX_PHOTOS} photos au maximum par fiche")
    nom = f"{datetime.datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}{extension}"
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / nom).write_bytes(octets)
    except OSError as e:
        return _json("500 Internal Server Error", erreur=f"impossible d'écrire la photo ({e.strerror or 'erreur'})")
    return _json("200 OK", nom=nom)


def vignette(conn, query, form, chantier_id, nom):
    dossier, _ = dossier_de(conn, chantier_id)
    octets = form.get("_octets")
    if dossier is None or not _nom_valide(nom) or not (dossier / nom).is_file():
        return _json("404 Not Found", erreur="photo introuvable")
    if not octets or len(octets) > LIMITE_VIGNETTE or format_de(octets) != ".jpg":
        return _json("400 Bad Request", erreur="vignette refusée")
    try:
        (dossier / VIGNETTES).mkdir(exist_ok=True)
        (dossier / VIGNETTES / (nom + ".jpg")).write_bytes(octets)
    except OSError as e:
        return _json("500 Internal Server Error", erreur=f"impossible d'écrire la vignette ({e.strerror or 'erreur'})")
    return _json("200 OK", nom=nom)


def supprimer(conn, query, form, chantier_id, nom):
    dossier, genre = dossier_de(conn, chantier_id)
    if dossier is None or not _nom_valide(nom):
        return gabarit("Introuvable", "<h1>Photo introuvable</h1>"), 404
    for fichier in (dossier / nom, dossier / VIGNETTES / (nom + ".jpg")):
        try:
            fichier.unlink()
        except OSError:
            pass
    return redirection(f"{url_fiche(chantier_id, genre)}?ok=photo_supprimee#photos")


ROUTES_PHOTOS = [
    ("GET", r"^/(?:soumission|chantier)/(\d+)/photos/([^/]+)$", lambda c, q, f, i, n: voir(c, q, int(i), n)),
    ("POST", r"^/(?:soumission|chantier)/(\d+)/photos$", lambda c, q, f, i: ajouter(c, q, f, int(i))),
    ("POST", r"^/(?:soumission|chantier)/(\d+)/photos/([^/]+)/vignette$", lambda c, q, f, i, n: vignette(c, q, f, int(i), n)),
    ("POST", r"^/(?:soumission|chantier)/(\d+)/photos/([^/]+)/supprimer$", lambda c, q, f, i, n: supprimer(c, q, f, int(i), n)),
]
