# app/ — appli Android de l'équipage (Capacitor + Firebase)

> Rule: update this file in the same commit as any feature change here.

Petite app Android pour que l'équipage alimente la carte du site : partage de
position (appli ouverte), édition PV, et **upload de photos EN GARDANT leur
localisation** — impossible via un navigateur sur Android depuis avril 2026
(le sélecteur de photos expurge le GPS pour tout ce qui n'a pas la permission
`ACCESS_MEDIA_LOCATION`, réservée aux apps installées). D'où une vraie app.

## iPhone = PWA (pas d'app native iOS)

Compiler une app iOS native exige un Mac + Xcode + compte Apple : hors budget.
Mais **iOS n'a pas le bug Android** (le sélecteur de photos garde le GPS EXIF),
donc la même UI web `www/` suffit sur iPhone en **PWA** : `manifest.json` +
balises `apple-mobile-web-app-*` + `apple-touch-icon` (icônes dans `icons/`).
Les utilisateurs iPhone ouvrent l'URL Pages de `www/` dans Safari →
« Partager » → « Sur l'écran d'accueil ». L'app s'ouvre alors plein écran, et
l'ajout de photos passe par le fallback `<input file>` + `exifr` (GPS conservé
sur iOS). Le plugin natif `AfricaMedia` n'existe que côté Android (APK).

## Pourquoi ces choix

- **Capacitor** : UI web (`www/`, vanilla, thème désert) + couche native
  minimale. Le natif ne sert qu'à une chose : lire le GPS EXIF des photos
  (permission `ACCESS_MEDIA_LOCATION` + `setRequireOriginal()` + `ExifInterface`).
- **Firebase** : Firestore (positions, PV, méta-photos). Serverless → rien à
  héberger. Le site lira ces données en direct.
- **Cloudinary** (fichiers photo) : Firebase Storage exige une carte (Blaze)
  sur les projets récents, refusé. On envoie donc les images sur Cloudinary
  via un **upload preset non signé** (gratuit, sans carte) ; seule l'URL
  `secure_url` retournée est stockée dans `photos/{id}` de Firestore.
- **Login = néant** : on choisit son prénom une fois, puis on retombe toujours
  dessus. Persistance = **cookie `crew-me`** (Max-Age 400 j, ré-écrit à chaque
  ouverture = fenêtre glissante) **+ miroir `localStorage`** ; on relit le
  cookie en priorité (`saveMe`/`loadMe`/`clearMe` dans `app.js`). Le cookie est
  là pour l'iPhone en PWA (« écran d'accueil »), où le localStorage peut être
  vidé. Le bouton **⇄** du header appelle `clearMe()` pour changer de perso.
  Firebase **Anonymous** connecte l'app en silence pour que les règles
  acceptent l'écriture. Pas de mot de passe, pas d'inscription.
- **Sécurité** volontairement légère (« délire entre potes ») : règles
  Firestore/Storage = lecture publique, écriture si `request.auth != null` +
  garde-fous de forme. Un APK décompilé pourrait écrire des bêtises ; assumé.

## Fichiers

- `www/index.html` / `styles.css` — 2 écrans : choix du prénom, puis dashboard
  (visage en haut, position, PV, mes photos). `<head>` porte le `manifest.json`
  + les balises `apple-mobile-web-app-*` (installable en PWA sur iPhone). Lien
  **retour au site** (`https://cartmanrolex.github.io/AfricaTrip/`, `target=_blank`)
  à deux endroits : bouton 🗺️ dans le header du dashboard + lien en pied des
  deux écrans (`.foot-link`).
- `www/manifest.json` + `www/icons/` — manifeste PWA + icônes (192/512 +
  `icon-180.png` pour l'apple-touch-icon). Icônes générées par un petit script
  Pillow (diamant orange sur fond désert), voir le commit d'origine.
- `www/faces.js` — `FACES` = photos de visage (data URIs) générées depuis
  `src/photos.json` ; affichées en haut du dashboard. Régénérer si les visages
  changent : voir la commande dans le commit d'origine (extrait de photos.json).
- `www/app.js` — Firebase (modular v10 via CDN gstatic), anon auth, `CREW`,
  `watchPosition` throttlé (écrit `positions/{nom}` + `tracks/{nom}/points`).
  **Position TOUJOURS active** tant que l'app est ouverte (pas de bouton) :
  indicateur `.live-card` (orbe pulsante) waiting/live/err + "envoyée il y a X".
  **PV auto-sauvegardés** dès qu'on les modifie (débounce 500ms → `crew/{nom}`
  merge) — pas de bouton, pas de XP ni compétence dans l'app (retirés). Le site
  lit `crew/{nom}.pv` en direct et **écrase** les PV du Sheet. **Mes
  photos** : `onSnapshot(photos where name==moi)` → grille live avec ✕ =
  `deleteDoc` (le fichier reste sur Cloudinary, la suppression Cloudinary
  exigerait la clé secrète non embarquée). **Deux voies d'ajout** : plugin natif
  `AfricaMedia.pickWithLocation()` (GPS fiable) sinon `<input file>` + `exifr`
  (fallback navigateur ; sur Android réel le GPS y serait expurgé). Accès
  plugins via helper `plugin()` (registerPlugin OU Capacitor.Plugins.X).
- `www/firebase-config.js` — clés Firebase + `CLOUDINARY` (cloudName, preset)
  + `CREW` (prénom → voiture). Clés non secrètes.
- `firestore.rules` — à coller dans la console Firebase (pas de storage.rules :
  on n'utilise pas Firebase Storage).
- `README.md` — setup Firebase (Gal, 5 min) + build APK (sur Basement) + distrib.

## Modèle de données Firestore

- `positions/{nom}` : `{name, car, lat, lng, at}` — dernière position (marqueurs live).
- `tracks/{nom}/points/{id}` : `{lat, lng, at}` — trace réelle parcourue.
- `crew/{nom}` : `{name, car, pv, at}` — PV live (le site les lit et écrase le
  Sheet). L'app n'écrit plus xp/skill.
- `photos/{id}` : `{name, car, url, lat, lng, gps, date, at}` — bulles carte
  (`url` = lien Cloudinary `secure_url` ; le fichier n'est pas dans Firebase).

## À faire (voir README « État »)

Plugin natif `AfricaMedia` (Kotlin) + build APK ; puis lecture live côté site
(`src/template.html`). Le build se fait sur **Basement** (le PC de Gal n'a pas
la chaîne Android). `node_modules/`, `android/`, `*.apk` sont git-ignorés.
