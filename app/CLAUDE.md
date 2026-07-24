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
  minimale. Le natif ne sert qu'à une chose : lire la localisation NON expurgée
  des médias (`ACCESS_MEDIA_LOCATION` + `setRequireOriginal()`). Photos : GPS
  EXIF via `ExifInterface`, fichier renvoyé en `base64`. Vidéos : GPS = atome
  ISO-6709 QuickTime via `MediaMetadataRetriever` (`METADATA_KEY_LOCATION`),
  fichier PAS en base64 (trop lourd) mais copié en cache → `path` file:// que
  le JS relit (`Capacitor.convertFileSrc`) puis uploade. Permission
  `READ_MEDIA_VIDEO` ajoutée. Le sélecteur accepte `image/*` + `video/*`.
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
- **Auth = UN mot de passe partagé** (Firebase Email/Password, un seul compte
  `AUTH_EMAIL` pour toute l'équipe). Demandé une fois (écran `#login`,
  `requireAuth()`/`showLogin()` dans `app.js`) ; Firebase garde la session, donc
  jamais reretapé sauf nouveau tel / cache vidé. Le mot de passe n'est **jamais**
  dans le code (tapé par l'user, haché par Firebase). Changer de perso (⇄) ne
  déconnecte pas. Pas d'inscription (à désactiver côté console).
- **Sécurité** : le site lit tout en public (aucune connexion), mais l'écriture
  est réservée à ce compte via `signed()` dans `firestore.rules`
  (`request.auth.token.email == AUTH_EMAIL`). Config Firebase publique = normal ;
  ce qui protège la carte, c'est le mot de passe. Résiduel assumé : Cloudinary
  reste en upload non signé, mais une image sans sa fiche Firestore
  (écriture protégée) n'apparaît nulle part → sans impact sur le site.

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
  photos** : `onSnapshot(photos where name==moi)` → `myDocs` (trié récent
  d'abord : date puis `at`), rendu par `renderMyPhotos()` : **sections par
  jour** (`dayLabel` : « Aujourd'hui » / « Hier » / date) + **filtre**
  `#mediafilter` (Tous / Photos / Vidéos, état `mediaFilter`) + compteur
  `#media-count`. ✕ = `deleteDoc` (le fichier reste sur Cloudinary, la
  suppression Cloudinary exigerait la clé secrète non embarquée). Tout est
  client, aucun changement de schéma → tient la charge quand il y a beaucoup
  de médias.
  **Légende** : taper sur une tuile ouvre `#media-modal` (`openMedia` → média
  en grand + `<input #media-caption>`) ; Enregistrer = `updateDoc` du seul
  champ `caption` (`initMediaModal`). Un badge 💬 marque les tuiles légendées.
  Le site affiche la légende dans la lightbox et en infobulle de bulle.
  ⚠️ Nécessite la règle Firestore `photos` en `allow update` restreint à
  `caption` (voir `firestore.rules`) — À PUBLIER dans la console. **Deux voies d'ajout** : plugin natif
  `AfricaMedia.pickWithLocation()` (GPS fiable) sinon `<input file>` + `exifr`
  (fallback navigateur ; sur Android réel le GPS y serait expurgé). Accès
  plugins via helper `plugin()` (registerPlugin OU Capacitor.Plugins.X).
  **Vidéos** (depuis 2026-07) : `<input accept="image/*,video/*">` accepte
  aussi la vidéo. `uploadPhoto(blob, lat, lng, date, video)` route vers
  l'endpoint Cloudinary `/video/upload` (vs `/image/upload`), cap
  `MAX_VIDEO_BYTES` = 100 Mo (limite upload non signé), et écrit
  `type:"video"` dans Firestore. Le GPS d'une vidéo n'est PAS lisible en
  navigateur (pas d'EXIF ; l'atome QuickTime n'est accessible qu'en natif) →
  vidéo sans position, placée par date (`file.lastModified`). La grille et la
  carte du site montrent un **poster** (1re frame, `so_0` + `.jpg`, helper
  `mediaThumb`) avec un badge ▶. Le preset Cloudinary non signé doit
  autoriser la ressource vidéo (à vérifier côté dashboard si un upload est
  rejeté).
  **Localisation manuelle** : si `uploadPhoto` reçoit `lat == null` (média sans
  GPS — typiquement toute vidéo web, ou photo dépouillée), un modal `#loc-modal`
  s'ouvre (`askLocation()`) : mini-carte Leaflet chargée À LA DEMANDE
  (`loadLeaflet`, CDN, rien au démarrage), on cadre sous une épingle centrale
  fixe (Valider = `map.getCenter()`) ou bouton « ◉ Ma position »
  (`navigator.geolocation`). Résout `{lat,lng}` → `manual:true`, ou `null`
  (Ignorer) → média sans lieu. S'applique aussi au natif si une photo/vidéo
  arrive sans GPS.
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
- `photos/{id}` : `{name, car, url, type, lat, lng, gps, manual, caption, date, at}`
  — bulles carte (`url` = lien Cloudinary `secure_url` ; le fichier n'est pas dans
  Firebase). `type` = `"image"` (défaut) ou `"video"` ; les anciens docs sans
  `type` sont traités comme image (sniff de l'URL `/video/upload/` en secours).
  `gps` = position issue du média (EXIF/atome) ; `manual` = position choisie à
  la main quand le média n'avait pas de GPS (le site affiche « position
  choisie » vs « estimée (convoi) »). Un média sans lat/lng n'apparaît PAS sur
  la carte (le lecteur live ignore les entrées sans position).

## À faire (voir README « État »)

Plugin natif `AfricaMedia` (Kotlin) + build APK ; puis lecture live côté site
(`src/template.html`). Le build se fait sur **Basement** (le PC de Gal n'a pas
la chaîne Android). `node_modules/`, `android/`, `*.apk` sont git-ignorés.
