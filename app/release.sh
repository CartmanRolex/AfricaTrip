#!/usr/bin/env bash
# Publie l'APK sur GitHub Releases.
#
#   bash app/release.sh "Titre de la release" [fichier-de-notes.md]
#
# Pourquoi ce script existe
# -------------------------
# L'équipage télécharge l'app par un lien PERMANENT :
#
#   https://github.com/CartmanRolex/AfricaTrip/releases/latest/download/expedition-afrique.apk
#
# GitHub résout ce lien par NOM DE FICHIER EXACT dans la dernière release. Une
# release publiée avec `expedition-afrique-2.9.0.apk` — un nom qui semble plus
# clair — casse donc le lien pour tout le monde, en silence : la release existe,
# elle s'affiche, seul le lien meurt. C'est arrivé avec la 2.9.0.
#
# Le nom du fichier n'est donc plus une décision : il est écrit ici une fois, et
# le script vérifie ensuite que le lien répond vraiment. Le seul test qui
# compte est celui de l'URL que les gens utilisent.
set -e
cd "$(dirname "$0")/.."

ASSET=expedition-afrique.apk     # NE PAS versionner ce nom : voir ci-dessus
APK=app/android/app/build/outputs/apk/debug/app-debug.apk
LIEN="https://github.com/CartmanRolex/AfricaTrip/releases/latest/download/$ASSET"

TITRE=${1:?usage: bash app/release.sh "Titre" [notes.md]}
NOTES=${2:-}

# La version vient du script de build, source unique. Deux endroits qui
# décident du numéro finiraient par ne plus être d'accord.
VERSION=$(grep -oP '^APP_VERSION_NAME=\K.*' app/build-android.sh)
TAG="app-v${VERSION}"
[ -f "$APK" ] || { echo "APK absente — lancer d'abord : bash app/build-android.sh"; exit 1; }

# L'APK contient-elle bien le code du dépôt ? Une release construite avant le
# dernier commit publierait l'ancienne app sous le nouveau numéro.
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
unzip -p "$APK" assets/public/app.js > "$TMP/embarque.js"
if ! diff -q app/www/app.js "$TMP/embarque.js" >/dev/null; then
  echo "L'APK ne contient pas le app.js actuel — relancer bash app/build-android.sh"; exit 1
fi

cp "$APK" "$TMP/$ASSET"
if gh release view "$TAG" >/dev/null 2>&1; then
  echo "Release $TAG déjà là — remplacement de l'asset."
  gh release upload "$TAG" "$TMP/$ASSET" --clobber
else
  if [ -n "$NOTES" ]; then
    gh release create "$TAG" "$TMP/$ASSET" --title "$TITRE" --notes-file "$NOTES"
  else
    gh release create "$TAG" "$TMP/$ASSET" --title "$TITRE" --generate-notes
  fi
fi

# LE contrôle : le lien que l'équipage utilise répond-il, et sert-il bien cette
# APK ? Tout le reste peut être vert et ce lien mort.
TAILLE_LOCALE=$(stat -c%s "$APK")
TAILLE_SERVIE=$(curl -sIL "$LIEN" | grep -i '^content-length' | tail -1 | tr -dc '0-9')
if [ "$TAILLE_LOCALE" != "$TAILLE_SERVIE" ]; then
  echo "Le lien permanent ne sert pas cette APK ($TAILLE_SERVIE vs $TAILLE_LOCALE octets) :"
  echo "  $LIEN"
  exit 1
fi
echo "Publié $TAG — le lien permanent sert bien l'APK ($TAILLE_LOCALE octets) :"
echo "  $LIEN"
