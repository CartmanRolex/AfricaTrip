"""
Verifie que les surcharges de `site-overrides.json` disent encore la verite.

Usage:  python src/check_overrides.py
Lit:    site-overrides.json + Firestore (chemins publics)
Sort:   code 1 si une surcharge est contredite par l'appli

Pourquoi ce fichier existe
--------------------------
`vehicle_from` a ete cree pour arbitrer du BRUIT : l'appli enregistre la
derniere voiture selectionnee, personne ne la remet a jour, et les points de
Hugo alternaient entre les deux voitures a deux secondes d'ecart. La surcharge
prime donc sur ce que l'appli a enregistre.

Mais elle n'a ni fin ni surveillance. Hugo et Paul ont echange une nuit puis
sont revenus ; le telephone de Paul l'a dit des le lendemain matin et l'a
repete vingt-sept fois. Le site a continue de les afficher intervertis pendant
deux jours, parce qu'une surcharge muette gagne meme quand elle a tort.

Ce qui vaut alerte, et ce qui n'en vaut PAS
-------------------------------------------
Premiere version de ce controle : « si les derniers releves contredisent tous
la surcharge, alerter ». C'etait faux, et les deux cas reels le montrent.

  Paul   surcharge hugodouard, ses releves disent hugodouard... puis paul-pot,
         et s'y tiennent. Il a VRAIMENT change de voiture. -> alerte justifiee.
  Hugo   surcharge hugodouard, ses releves disent paul-pot depuis toujours.
         Il est pourtant bien dans Hugodouard : il n'a simplement jamais
         remis a jour son reglage depuis l'echange. -> alerter serait absurde,
         c'est exactement le bruit que la surcharge est la pour couvrir.

Le signal n'est donc pas le DESACCORD, c'est le CHANGEMENT. Un desaccord
permanent est un reglage que personne ne touche — l'etat normal, et la raison
d'etre de la surcharge. Un basculement, lui, est un geste : quelqu'un a ouvert
l'appli et change sa voiture, et ca, ca veut dire quelque chose.

Le controle cherche donc, APRES l'instant de la surcharge, une bascule qui
part de la voiture imposee et n'y revient pas. Un desaccord constant est
seulement signale, sans faire echouer quoi que ce soit.

Il tourne en DERNIER dans le workflow, apres la publication, et volontairement
bloquant : le site est deja a jour, l'echec ne sert qu'a envoyer le mail. Il ne
corrige rien tout seul — l'equipage seul sait qui roule ou.
"""
import datetime, json, os, sys

from fetch_routes import TRIP_ID, fields, firebase_config, fs_list
# Ces trois calculs etaient recopies ici. La copie locale de la lecture de
# date OUBLIAIT le fuseau : chaque media etait date de deux heures trop tot,
# soit ~180 km, et le controle les comparait aux points GPS du mauvais
# moment. Voir `commun.py`.
from commun import ms_utc as instant, vehicle_id

HERE = os.path.dirname(os.path.abspath(__file__))
OVERRIDES = os.path.join(HERE, "site-overrides.json")

# Combien de releves concordants apres la bascule avant de la croire. Assez
# pour qu'une fausse manoeuvre isolee ne declenche rien, assez peu pour qu'un
# vrai changement soit vu dans la journee.
CONSENSUS = 4


def releves(project, key, noms):
    """Ce que chaque personne a produit elle-meme : [(instant, voiture)] trie.

    Les points ecrits depuis le telephone de QUELQU'UN D'AUTRE sont ecartes :
    changer d'identite dans l'appli ecrivait un point sous le nouveau nom, et
    un seul telephone a ainsi signe quatre personnes en onze secondes.
    """
    pts = {n: [] for n in noms}
    for doc in fs_list(project, key, f"trips/{TRIP_ID}/trackChunks"):
        for p in (fields(doc).get("points") or {}).values():
            nom, ms = p.get("displayName"), p.get("capturedAtMs")
            if nom in pts and ms is not None:
                pts[nom].append((float(ms), vehicle_id(p.get("vehicleId")), p.get("deviceId")))

    out = {}
    for nom, liste in pts.items():
        # Le telephone de la personne = celui qui a ecrit le plus sous son nom.
        compte = {}
        for _, _, dev in liste:
            compte[dev] = compte.get(dev, 0) + 1
        sien = max(compte, key=compte.get) if compte else None
        out[nom] = [(ms, v) for ms, v, dev in liste if v and dev == sien]

    for doc in fs_list(project, key, "photos"):
        f = fields(doc)
        nom = f.get("displayName") or f.get("name")
        ms = instant(f.get("capturedAt"))
        v = vehicle_id(f.get("vehicleIdAtCapture") or f.get("car"))
        if nom in out and ms is not None and v:
            out[nom].append((ms, v))

    for nom in out:
        out[nom].sort()
    return out


def bascule(suite, impose):
    """La suite quitte-t-elle `impose` sans y revenir ?

    Renvoie la voiture vers laquelle elle bascule, ou None. Une suite qui ne
    contient JAMAIS `impose` n'est pas une bascule : c'est un reglage que
    personne n'a touche depuis, et c'est precisement ce que la surcharge couvre.
    """
    vus = [v for _, v in suite]
    if impose not in vus:
        return None
    apres = vus[len(vus) - 1 - vus[::-1].index(impose) + 1:]
    if len(apres) >= CONSENSUS and len(set(apres)) == 1:
        return apres[0]
    return None


def main():
    with open(OVERRIDES, encoding="utf-8") as f:
        vf = (json.load(f).get("vehicle_from") or {})
    if not vf:
        print("Aucune surcharge de voiture — rien a verifier.")
        return 0

    project, key = firebase_config()
    tout = releves(project, key, set(vf))

    problemes = []
    for nom, entrees in sorted(vf.items()):
        if not entrees:
            continue
        impose = sorted(entrees, key=lambda e: e["at"])[-1]
        depuis = datetime.datetime.fromisoformat(
            impose["at"] if len(impose["at"]) > 10 else impose["at"] + "T00:00").timestamp() * 1000
        suite = [(ms, v) for ms, v in tout.get(nom, []) if ms >= depuis]
        vers = bascule(suite, impose["vehicle"])
        if vers:
            problemes.append((nom, impose, vers))
            print(f"{nom:8} {impose['vehicle']:11} BASCULE VERS {vers} — "
                  f"{len(suite)} releves depuis {impose['at']}")
        elif suite and impose["vehicle"] not in {v for _, v in suite}:
            print(f"{nom:8} {impose['vehicle']:11} ok — l'appli dit "
                  f"{suite[-1][1]} depuis {impose['at']} sans jamais changer "
                  f"(reglage laisse tel quel, c'est ce que la surcharge couvre)")
        else:
            print(f"{nom:8} {impose['vehicle']:11} ok — {len(suite)} releves concordants")

    if problemes:
        print("\nUne surcharge `vehicle_from` a survecu au fait qu'elle decrivait.")
        for nom, impose, vers in problemes:
            print(f"  {nom} : le site l'affiche dans {impose['vehicle']} depuis "
                  f"{impose['at']}, mais son telephone est passe a {vers} et s'y tient.")
        print("Corriger src/site-overrides.json : ajouter une entree "
              "{\"at\": \"<quand>\", \"vehicle\": \"<voiture>\"} pour clore la surcharge.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
