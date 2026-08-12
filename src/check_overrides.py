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

Mais elle n'avait ni fin ni surveillance. Hugo et Paul ont echange une nuit
puis sont revenus dans leur voiture ; le telephone de Paul l'a dit des le
lendemain matin et l'a repete vingt-sept fois de suite. Le site a continue de
les afficher intervertis pendant deux jours, parce qu'une surcharge muette
gagne meme quand elle a tort.

Une surcharge est faite pour trancher du desaccord, pas pour ecraser un
consensus. Ce controle regarde donc les DERNIERS releves signes par la
personne — points GPS et medias confondus — et echoue si tous, sans exception,
contredisent la voiture imposee. Il tourne en DERNIER dans le workflow, apres
la publication : la mise a jour du site a donc deja eu lieu, et l'echec du job
ne sert qu'a envoyer le mail qui dit d'aller corriger le fichier.

Il ne corrige rien tout seul, volontairement : c'est l'equipage qui sait qui
roule ou. Il rend seulement impossible de ne pas s'en apercevoir.
"""
import json, os, sys

from fetch_routes import TRIP_ID, fields, firebase_config, fs_list

HERE = os.path.dirname(os.path.abspath(__file__))
OVERRIDES = os.path.join(HERE, "site-overrides.json")

# Combien de releves concordants font un consensus. Assez pour qu'une fausse
# manoeuvre isolee — ou un glissement d'identite — ne renverse pas une
# surcharge, assez peu pour qu'un vrai changement soit vu dans la journee.
CONSENSUS = 6


def vehicle_id(value):
    """Meme normalisation que le front (`vehicleId()`), en plus court."""
    v = str(value or "").strip().lower().replace(" ", "-")
    if v in ("hugodouard", "1", "car-1", "voiture-1"):
        return "hugodouard"
    if v in ("paul-pot", "paulpot", "2", "car-2", "voiture-2"):
        return "paul-pot"
    return None


def releves(project, key, noms):
    """Tout ce que l'appli a enregistre par personne : (instant, voiture)."""
    out = {n: [] for n in noms}
    for doc in fs_list(project, key, f"trips/{TRIP_ID}/trackChunks"):
        f = fields(doc)
        for p in (f.get("points") or {}).values():
            nom, ms = p.get("displayName"), p.get("capturedAtMs")
            if nom in out and ms is not None:
                out[nom].append((float(ms), vehicle_id(p.get("vehicleId"))))
    for doc in fs_list(project, key, "photos"):
        f = fields(doc)
        nom, at = f.get("displayName") or f.get("name"), f.get("capturedAt")
        if nom in out and at:
            # `capturedAt` est un timestamp ISO ; on ne compare que des ordres.
            out[nom].append((at, vehicle_id(f.get("vehicleIdAtCapture") or f.get("car"))))
    # Les deux sources ont des instants de types differents (ms / ISO) : on les
    # trie separement puis on fusionne sur la seule chose qui compte ici,
    # l'ordre chronologique de chaque source prise a part.
    for n in out:
        pts = sorted((x for x in out[n] if isinstance(x[0], float)))
        med = sorted((x for x in out[n] if not isinstance(x[0], float)))
        out[n] = [v for _, v in pts if v][-CONSENSUS:] + [v for _, v in med if v][-CONSENSUS:]
    return out


def main():
    with open(OVERRIDES, encoding="utf-8") as f:
        vf = (json.load(f).get("vehicle_from") or {})
    if not vf:
        print("Aucune surcharge de voiture — rien a verifier.")
        return 0

    project, key = firebase_config()
    derniers = releves(project, key, set(vf))

    problemes = []
    for nom, entrees in vf.items():
        if not entrees:
            continue
        impose = sorted(entrees, key=lambda e: e["at"])[-1]   # la surcharge en cours
        vus = derniers.get(nom) or []
        if len(vus) < CONSENSUS:
            print(f"{nom:8} surcharge {impose['vehicle']:11} "
                  f"({len(vus)} releve(s) seulement — pas de quoi conclure)")
            continue
        contre = [v for v in vus if v != impose["vehicle"]]
        if len(contre) == len(vus):
            problemes.append((nom, impose, vus))
            print(f"{nom:8} surcharge {impose['vehicle']:11} CONTREDITE : "
                  f"{len(vus)} derniers releves disent tous {vus[-1]}")
        else:
            print(f"{nom:8} surcharge {impose['vehicle']:11} coherente "
                  f"({len(vus) - len(contre)}/{len(vus)} releves d'accord)")

    if problemes:
        print("\nUne surcharge `vehicle_from` a survecu au fait qu'elle decrivait.")
        for nom, impose, vus in problemes:
            print(f"  {nom} : le site l'affiche dans {impose['vehicle']} depuis "
                  f"{impose['at']}, son telephone dit {vus[-1]}.")
        print("Corriger src/site-overrides.json : ajouter une entree "
              "{\"at\": \"<quand>\", \"vehicle\": \"<voiture>\"} pour clore la surcharge.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
