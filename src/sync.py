"""
Met a jour le site en une seule commande.

Usage:  python src/sync.py          (ou double-clic sur sync.bat a la racine)

1. parse_csv.py    : relit les donnees du voyage (data/*.csv + overrides)
2. fetch_routes.py : calcule la route reelle entre les nouveaux points GPS
3. build.py        : regenere le site
4. fetch_photos.py : rapatrie les nouvelles photos du Drive partage
5. git commit+push : publie sur GitHub Pages

Le Google Sheet n'est PLUS la reference : les donnees du voyage vivent dans le
depot (data/*.csv + src/site-overrides.json). sync.py ne telecharge donc plus
rien depuis le Sheet — sinon un double-clic ecraserait les donnees a jour par
une feuille abandonnee. Pour reimporter volontairement depuis le Sheet :
`python src/refresh.py --from-sheet`.

Le commit n'ajoute QUE les fichiers produits par le pipeline (liste PUBLISH
ci-dessous) — jamais photos/gal.enc ni les fichiers locaux git-ignores.
S'il n'y a rien de nouveau, le script s'arrete sans commit.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))

PUBLISH = ["index.html", "voyage-afrique.html", "src/data.json",
           "src/gallery.json", "src/photos.json", "src/routes.json",
           "src/site-overrides.json", "data", "photos/uploads"]


def run(*cmd):
    print(f"\n$ {' '.join(os.path.basename(c) if os.sep in c else c for c in cmd)}")
    return subprocess.run(cmd, cwd=ROOT).returncode


def main():
    if run(sys.executable, os.path.join(HERE, "parse_csv.py")):
        sys.exit("ERREUR pendant la lecture des donnees du voyage (data/*.csv).")
    # Le routage n'est pas bloquant : sans reseau on garde les routes deja
    # connues et les nouveaux segments restent des lignes droites.
    if run(sys.executable, os.path.join(HERE, "fetch_routes.py")):
        print("AVERTISSEMENT : routes non mises a jour, on continue.")
    if run(sys.executable, os.path.join(HERE, "build.py")):
        sys.exit("ERREUR pendant la generation du site.")
    if run(sys.executable, os.path.join(HERE, "fetch_photos.py")):
        sys.exit("ERREUR pendant la synchro des photos Drive.")

    changed = subprocess.run(["git", "status", "--porcelain", "--"] + PUBLISH,
                             cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if not changed:
        print("\nRien de nouveau — le site est deja a jour.")
        return
    print("\nChangements a publier :\n" + changed)
    if run("git", "add", "--", *PUBLISH):
        sys.exit("ERREUR git add.")
    if run("git", "commit", "-m", "Sync du site (donnees du depot + photos partagees)"):
        sys.exit("ERREUR git commit.")
    if run("git", "push"):
        sys.exit("ERREUR git push (reseau ? credentials ?).")
    print("\nOK — site publie, en ligne dans ~1 minute.")


if __name__ == "__main__":
    main()
