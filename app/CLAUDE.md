# app/ — appli Android de l'équipage (Capacitor + Firebase)

> Rule: update this file in the same commit as any feature change here.

Petite app Android pour que l'équipage alimente la carte du site : partage de
position (appli ouverte), édition PV/XP, et **upload de photos EN GARDANT leur
localisation** — impossible via un navigateur sur Android depuis avril 2026
(le sélecteur de photos expurge le GPS pour tout ce qui n'a pas la permission
`ACCESS_MEDIA_LOCATION`, réservée aux apps installées). D'où une vraie app.

## Pourquoi ces choix

- **Capacitor** : UI web (`www/`, vanilla, thème désert) + couche native
  minimale. Le natif ne sert qu'à une chose : lire le GPS EXIF des photos
  (permission `ACCESS_MEDIA_LOCATION` + `setRequireOriginal()` + `ExifInterface`).
- **Firebase** : Firestore (positions, PV, méta-photos) + Storage (fichiers).
  Serverless → rien à héberger. Le site lira ces données en direct.
- **Login = néant** : on choisit son prénom (stocké en `localStorage`), et
  Firebase **Anonymous** connecte l'app en silence pour que les règles
  acceptent l'écriture. Pas de mot de passe, pas d'inscription.
- **Sécurité** volontairement légère (« délire entre potes ») : règles
  Firestore/Storage = lecture publique, écriture si `request.auth != null` +
  garde-fous de forme. Un APK décompilé pourrait écrire des bêtises ; assumé.

## Fichiers

- `www/index.html` / `styles.css` — 2 écrans : choix du prénom, puis dashboard
  (position, PV/XP, photos).
- `www/app.js` — Firebase (modular v10 via CDN gstatic), anon auth, `CREW`,
  `watchPosition` throttlé (écrit `positions/{nom}` + `tracks/{nom}/points`),
  save `crew/{nom}`, upload photos. **Deux voies photo** : `window.AfricaMedia
  .pickWithLocation()` (plugin natif, GPS fiable) sinon `<input file>` + `exifr`
  (fallback navigateur pour tester ; sur Android réel le GPS y serait expurgé).
- `www/firebase-config.js` — clés Firebase (non secrètes) + `CREW` (prénom →
  voiture). **À remplir** (README étape 1).
- `firestore.rules` / `storage.rules` — à coller dans la console Firebase.
- `README.md` — setup Firebase (Gal, 5 min) + build APK (sur Basement) + distrib.

## Modèle de données Firestore

- `positions/{nom}` : `{name, car, lat, lng, at}` — dernière position (marqueurs live).
- `tracks/{nom}/points/{id}` : `{lat, lng, at}` — trace réelle parcourue.
- `crew/{nom}` : `{name, car, pv, xp, skill, at}` — stats live.
- `photos/{id}` : `{name, car, url, lat, lng, gps, date, at}` — bulles carte.
- Storage `photos/{nom}/{fichier}.jpg`.

## À faire (voir README « État »)

Plugin natif `AfricaMedia` (Kotlin) + build APK ; puis lecture live côté site
(`src/template.html`). Le build se fait sur **Basement** (le PC de Gal n'a pas
la chaîne Android). `node_modules/`, `android/`, `*.apk` sont git-ignorés.
