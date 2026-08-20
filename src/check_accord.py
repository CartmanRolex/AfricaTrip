"""
Verifie que Python et le site donnent la MEME reponse sur les calculs de base.

Usage:  python src/check_accord.py     # code 1 si les deux mondes divergent

Pourquoi ce fichier existe
--------------------------
`commun.py` a rassemble en une seule ecriture les trois calculs elementaires du
cote Python : distance entre deux points, normalisation de voiture, lecture
d'une date. Mais le site (`template.html`) et l'appli (`app/www/app.js`)
tournent dans un navigateur : **on ne partage pas du code entre Python et
JavaScript.** Il restera donc toujours deux implementations.

Ce qu'on ne peut pas unifier, on l'empeche de deriver. Ce controle donne les
memes entrees aux deux mondes et compare les sorties.

Ce n'est pas theorique. Les deux bugs qui ont motive tout ce travail etaient
exactement ca : une copie corrigee, l'autre pas.
  * une lecture de date sans fuseau, decalee de deux heures — soit ~180 km au
    rythme d'une voiture — avec un symptome trompeur : l'erreur ne diminuait
    pas quand le point de trace se rapprochait, ce qui est impossible ;
  * `car-1` reconnu d'un cote, ignore de l'autre.

Le site est la reference : c'est lui qui dessine. Quand ce controle echoue,
c'est Python qu'on aligne, sauf preuve du contraire.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from commun import hav_km, ms_utc, vehicle_id  # noqa: E402

TEMPLATE = os.path.join(HERE, "template.html")

# Des cas choisis pour ce qu'ils cassent, pas pour faire nombre : deux points
# du voyage, deux points quasi confondus (le cas ou l'arrondi decide), un
# passage de l'equateur et du meridien, et toutes les generations d'identifiant
# de voiture.
DISTANCES = [
    ((46.2044, 6.1432), (43.2965, 5.3698)),      # Geneve -> Marseille
    ((31.6295, -7.9811), (33.5731, -7.5898)),    # Marrakech -> Casablanca
    ((30.5759, -9.3451), (30.5741, -9.3444)),    # 200 m, la ou l'arrondi joue
    ((0.0, 0.0), (0.0, 1.0)),                    # equateur
    ((-33.9, 18.4), (35.7, 139.7)),              # antipodique, presque
    ((36.7490, -4.3919), (36.7490, -4.3919)),    # distance nulle
]
VOITURES = ["hugodouard", "paul-pot", "PaulPot", "1", "2", "car-1", "car-2",
            "voiture-1", "Voiture-2", " hugodouard ", "obs", "", None, "n'importe quoi"]
DATES = ["2026-08-11T15:38:05Z", "2026-08-11T15:38:05.123Z",
         "2026-08-11T17:38:05+02:00", "2026-08-11T15:38:05", "2026-08-11",
         1786462685000, "", None, "pas une date"]


def cote_js():
    """Extrait `hav`, `vehicleId` et `toMs` du template et les execute sous Node.

    On lit les fonctions DANS le template plutot que d'en recopier une version
    de test : une copie de test qui derive ne prouve plus rien.
    """
    src = open(TEMPLATE, encoding="utf-8").read()

    def bloc(entete):
        """Extrait une fonction en equilibrant ses accolades.

        Chercher un `\n}` ne marche pas : `hav` se termine par `;}` en fin de
        ligne, et la recherche emportait alors tout le code qui suit.
        """
        i = src.index(entete)
        j = src.index("{", i)
        n = 0
        while j < len(src):
            if src[j] == "{":
                n += 1
            elif src[j] == "}":
                n -= 1
                if n == 0:
                    return src[i:j + 1]
            j += 1
        raise SystemExit(f"Fonction non refermee : {entete}")

    def expression(entete, fin=";"):
        """Extrait une const flechee, qui n'a pas d'accolade de fin propre."""
        i = src.index(entete)
        j = src.index(fin, src.index("\n", i))
        return src[i:j + 1]

    code = "\n".join([
        # Les dependances d'abord : `vehicleId` s'appuie sur `slug`, `toMs` sur
        # `firstValue`. On les prend AUSSI dans le template — recopier une
        # dependance ici rouvrirait la porte a la derive qu'on ferme.
        expression("const slug = s =>"),
        bloc("function firstValue("),
        bloc("function hav(a,b){"),
        bloc("function vehicleId(v){"),
        bloc("function toMs(v){"),
        "const dist=" + json.dumps(DISTANCES) + ";",
        "const voit=" + json.dumps(VOITURES) + ";",
        "const dates=" + json.dumps(DATES) + ";",
        "console.log(JSON.stringify({",
        "  distances: dist.map(([a,b])=>hav({lat:a[0],lng:a[1]},{lat:b[0],lng:b[1]})),",
        "  voitures: voit.map(v=>vehicleId(v)||null),",
        "  dates: dates.map(d=>toMs(d)||null),",
        "}));",
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(code)
        chemin = f.name
    try:
        out = subprocess.run(["node", chemin], capture_output=True, text=True, timeout=60)
        if out.returncode:
            raise SystemExit("Le code du site n'a pas pu etre execute :\n" + out.stderr[:800])
        return json.loads(out.stdout)
    finally:
        os.unlink(chemin)


def main():
    js = cote_js()
    ecarts = []

    print("Distances (km) — le site contre Python :")
    for (a, b), attendu in zip(DISTANCES, js["distances"]):
        obtenu = hav_km(a, b)
        # Un metre d'ecart sur des milliers de kilometres est du bruit de
        # virgule flottante, pas une divergence de logique.
        ok = abs(obtenu - attendu) < 0.001
        if not ok:
            ecarts.append(f"distance {a}->{b} : site {attendu}, Python {obtenu}")
        print(f"  {obtenu:12.4f}  {'ok' if ok else 'DIVERGENCE'}")

    print("\nVoitures :")
    for v, attendu in zip(VOITURES, js["voitures"]):
        obtenu = vehicle_id(v)
        ok = obtenu == attendu
        if not ok:
            ecarts.append(f"voiture {v!r} : site {attendu!r}, Python {obtenu!r}")
        print(f"  {str(v)[:16]:18} -> {str(obtenu):12} {'ok' if ok else 'DIVERGENCE (site: %r)' % attendu}")

    print("\nDates (millisecondes UTC) :")
    for d, attendu in zip(DATES, js["dates"]):
        obtenu = ms_utc(d)
        ok = (obtenu is None and attendu is None) or (
            obtenu is not None and attendu is not None and abs(obtenu - attendu) < 1)
        if not ok:
            ecarts.append(f"date {d!r} : site {attendu}, Python {obtenu}")
        print(f"  {str(d)[:30]:32} -> {str(obtenu):18} {'ok' if ok else 'DIVERGENCE (site: %s)' % attendu}")

    if ecarts:
        print(f"\n{len(ecarts)} divergence(s) entre le site et Python :")
        for e in ecarts:
            print("  " + e)
        print("\nLe site est la reference : c'est lui qui dessine. Aligner "
              "src/commun.py, sauf preuve que le site a tort.")
        return 1
    print("\nLes deux mondes sont d'accord sur les trois calculs de base.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
