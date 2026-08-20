"""
Applique un plan de repositionnement de medias dans Firestore.

Usage:  python src/apply_positions.py <plan.json>            # apercu
        python src/apply_positions.py <plan.json> --commit    # applique
        python src/apply_positions.py <plan.json> --revert    # apercu du retour
        python src/apply_positions.py <plan.json> --revert --commit

Le plan est une liste d'objets :
    {"id": "<doc>", "avant": [lat, lng], "apres": [lat, lng], ...}

`avant` est la sauvegarde : c'est ce qui rend l'operation reversible, et c'est
pourquoi le plan est COMMITE dans le depot plutot que jete apres usage.
Firestore ne garde pas d'historique ; sans ce fichier, l'ancien point est perdu.

Pourquoi ce script existe
-------------------------
Certains equipiers placent l'epingle sur un repere approximatif — une ville
connue — plutot que sur l'endroit reel. Mesure sur les medias de Jehan : huit
d'entre eux partagent EXACTEMENT les memes coordonnees alors que la voiture
etait 165 a 215 km plus loin, et quatre autres se partagent un second point.
Ce n'est pas une erreur ponctuelle, c'est une facon de faire.

Quand la trace de la voiture porte un point proche dans le temps, elle dit
mieux que l'epingle ou le media a ete pris (mediane mesuree : 0,05 km sous
30 min d'ecart, voir `app/CLAUDE.md`). Le plan est calcule avec la logique du
SITE — `vehiclePoints()`, garde-fous compris — et pas avec une reimplementation
Python, qui s'etait deja fait piéger par des points parasites.

Ce qui n'est PAS touche
-----------------------
`locationSource` reste `manual`, avec `gps:false` et `manual:true`. Des trois
valeurs que les regles autorisent (`media-gps | manual | none`), c'est la seule
honnete : la position ne vient pas du media lui-meme. La marquer `media-gps`
serait affirmer un GPS qui n'existe pas.
"""
import argparse, json, os, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fix_video_dates import jeton  # noqa: E402
from fetch_routes import firebase_config  # noqa: E402


def ecrire(token, project, doc_id, lat, lng):
    """Patch cible : lat/lng seuls. Le reste du document est intouche."""
    url = (f"https://firestore.googleapis.com/v1/projects/{project}/databases/"
           f"(default)/documents/photos/{doc_id}"
           "?updateMask.fieldPaths=lat&updateMask.fieldPaths=lng")
    corps = json.dumps({"fields": {"lat": {"doubleValue": lat},
                                   "lng": {"doubleValue": lng}}}).encode()
    req = urllib.request.Request(url, data=corps, method="PATCH",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("plan", help="fichier JSON du plan")
    ap.add_argument("--commit", action="store_true", help="ecrire (sinon apercu)")
    ap.add_argument("--revert", action="store_true", help="remettre les positions d'origine")
    args = ap.parse_args()

    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    depart, arrivee = ("apres", "avant") if args.revert else ("avant", "apres")
    sens = "RETOUR aux positions d'origine" if args.revert else "repositionnement"
    print(f"{len(plan)} medias — {sens}\n")

    grands = sorted(plan, key=lambda e: -e.get("deplacementKm", 0))[:10]
    print("  Les dix plus gros deplacements :")
    for e in grands:
        a, b = e[depart], e[arrivee]
        print(f"    {e['id'][:26]:26} {a[0]:8.3f},{a[1]:8.3f} -> {b[0]:8.3f},{b[1]:8.3f}"
              f"   ({e.get('deplacementKm', 0):.0f} km, point a {e.get('ecartMin', '?')} min)")

    if not args.commit:
        print("\n[APERCU] Rien ecrit. Ajouter --commit pour appliquer.")
        return

    project, _ = firebase_config()
    token = jeton()
    faits = 0
    for e in plan:
        lat, lng = e[arrivee]
        try:
            ecrire(token, project, e["id"], float(lat), float(lng))
            faits += 1
        except urllib.error.HTTPError as err:
            print(f"  echec sur {e['id']} : {err.code} {err.reason}")
    print(f"\n{faits}/{len(plan)} medias repositionnes.")
    print("Le site les reprendra au prochain instantane horaire "
          "(ou lancer : python src/fetch_tracks.py && python src/build.py).")


if __name__ == "__main__":
    main()
