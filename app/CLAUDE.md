# app/ — application équipage (Capacitor + Firebase)

> Rule: update this file in the same commit as any feature change here.

Application utilisée par chaque membre de l'équipage pour déclarer son mode de
déplacement, partager sa propre position, modifier ses PV et publier des
photos/vidéos localisées. Il n'existe aucune balise dédiée aux voitures : le
site reconstruit leurs trajets à partir des points des personnes qui avaient
déclaré être dans la voiture au moment de la capture.

Le même `www/` sert dans l'APK Android (Capacitor) et dans la PWA iPhone. Le
suivi GPS est actif uniquement pendant que l'application est ouverte et que le
mode n'est pas **Pause**.

## Parcours utilisateur v2

1. L'utilisateur choisit son prénom. Ce choix est gardé dans le cookie
   `crew-me` (400 jours, expiration repoussée) avec un miroir `localStorage`.
2. L'application exige le compte Firebase Email/Password partagé
   `equipage@expedition-afrique.app`. Le mot de passe n'est jamais dans le
   dépôt ; Firebase conserve ensuite la session. Le bouton **⇄** change de
   personne sans déconnecter le compte partagé.
3. Le dashboard propose quatre affectations persistantes, propres à chaque
   personne : **Hugodouard**, **Paul Pot**, **À pied / autre**, **Pause**.
   Le choix est conservé par cookie + `localStorage`. Sans choix mémorisé, le
   mode sûr par défaut est Pause.
4. Toute nouvelle session et tout changement créent un événement immuable dans
   `assignmentEvents`. Le GPS ne démarre qu'après mise en file locale durable de
   cet événement. Changer d'affectation arrête d'abord l'ancien watcher et
   exige un premier fix frais (`maximumAge: 0`) pour ne pas ré-étiqueter une
   position mise en cache sous l'ancienne voiture ; Pause n'enregistre aucun
   point.
5. Chaque point reste personnel et embarque un instantané de l'affectation
   (`personId`, `vehicleId`, `mode`, `assignmentId`). Le site peut donc afficher
   le trajet d'une personne sans le mélanger et dériver séparément celui de
   chaque voiture.

## Suivi GPS et file hors ligne

- `watchPosition` utilise le plugin Capacitor Geolocation dans l'APK et
  `navigator.geolocation` dans la PWA.
- Les coordonnées invalides et les fixes d'une précision supérieure à 250 m
  sont ignorés. Les métriques optionnelles conservées sont `accuracyM`,
  `speedMps` et `headingDeg`.
- Cadence maximale : un point par minute en mouvement ; à moins de 25 m du
  dernier point mis en file, un rappel toutes les cinq minutes.
- Les points et affectations passent d'abord dans une outbox IndexedDB
  (`africa-trip-01-outbox-v2`). `localStorage` sert de secours si IndexedDB est
  indisponible. Les identifiants sont stables, la livraison est FIFO et les
  écritures Firestore sont idempotentes. Une entrée n'est retirée qu'après
  succès ; les erreurs réseau ou de règles sont réessayées avec backoff jusqu'à
  60 s, sans suppression silencieuse.
- Les chunks sont séparés par personne, session, affectation et fenêtre de deux
  heures. À la cadence client normale, ils contiennent au plus 120 points ; les
  règles gardent un plafond de 160. `latest/{personId}` n'accepte qu'un point
  plus récent ou un retry strictement identique.
- Les watchers, timers et listeners Firestore sont nettoyés au changement de
  personne. Les callbacks asynchrones capturent l'identité et la session pour
  ne jamais attribuer un point au mauvais utilisateur.

## Authentification et sécurité

- Auth active : **Firebase Email/Password**, avec un unique compte partagé dont
  l'email est `AUTH_EMAIL` dans `www/firebase-config.js`.
- Aucune inscription n'est exposée dans l'application.
- `firestore.rules` autorise les écritures uniquement si le token porte cet
  email exact. Les lectures nécessaires au site public restent anonymes.
- Les règles v2 valident le voyage `africa-trip-01`, le roster, la cohérence
  prénom/personId, l'affectation voiture/mode, les coordonnées, la précision,
  les timestamps et les champs autorisés. Les événements sont immuables et un
  chunk ne peut être enrichi que d'un nouveau point cohérent avec ses champs de
  tête.
- Les chemins historiques `positions`, `tracks` et les anciens formats de
  `photos` restent autorisés pour la compatibilité des anciennes versions. Ils
  ne sont plus le modèle écrit par l'application v2.

Publier les règles depuis la racine du dépôt, avant de distribuer l'app v2 :

```bash
firebase login
firebase use africatrip-eea1a
firebase deploy --only firestore:rules
```

La racine contient `firebase.json` (source `app/firestore.rules`) et
`.firebaserc` (projet par défaut `africatrip-eea1a`). Vérifier le diff et les
tests des règles avant tout déploiement.

## Modèle Firestore actif

- `trips/africa-trip-01/assignmentEvents/{assignmentId}` : événement
  d'affectation immuable avec identité, `vehicleId`, `mode`, instant effectif,
  session, appareil et raison (`session-start` ou `user-change`). Lecture
  réservée au compte équipage.
- `trips/africa-trip-01/trackChunks/{chunkId}` : document personnel homogène
  pour une session + une affectation + une fenêtre de deux heures. Les points
  sont une map indexée par `pointId`; les champs de tête incluent identité,
  session, appareil, affectation, voiture, mode et début de fenêtre.
- `trips/africa-trip-01/latest/{personId}` : dernier point v2 exact d'une
  personne, lu publiquement par le site.
- `crew/{nom}` : `{name, car, pv, at}`. L'app n'écrit plus XP/compétence ; le
  site applique les PV Firestore par-dessus ceux du Sheet.
- `photos/{id}` : champs historiques
  `{name, car, url, type, lat, lng, gps, manual, caption?, date, at}` plus le
  contexte v2 `{tripId, personId, displayName, vehicleIdAtCapture, mode,
  assignmentId, capturedAt, locationSource}`. `locationSource` vaut
  `media-gps`, `manual` ou `none`.

## Médias

- Les fichiers vont sur Cloudinary via le preset non signé `expedition` ; seul
  le `secure_url` et les métadonnées vont dans Firestore. Firebase Storage n'est
  pas utilisé.
- Android : le plugin Java `native/AfricaMediaPlugin.java` récupère l'original
  grâce à `ACCESS_MEDIA_LOCATION`. Il lit l'EXIF des images et l'atome de lieu
  QuickTime des vidéos. Il transmet désormais `capturedAt` avec l'heure EXIF/
  QuickTime complète (et l'offset quand il existe), au lieu de tronquer au jour
  puis de faire classer chaque média à midi dans la reconstruction du trajet.
  Une vidéo est copiée en cache et relue via
  `Capacitor.convertFileSrc` au lieu d'être renvoyée en base64.
- PWA : `<input type=file>` + `exifr` pour les images. Le navigateur ne lit pas
  la position QuickTime des vidéos.
- Si le média n'a pas de lieu, `askLocation()` ouvre une carte Leaflet chargée
  à la demande. L'utilisateur peut aussi ignorer puis ajouter/modifier le lieu
  depuis le détail du média. L'édition ne change que la légende ou les champs de
  lieu autorisés par les règles.
- L'ajout est désactivé pendant une transition d'affectation. Le contexte
  personne/voiture est capturé avant les opérations asynchrones afin qu'un
  changement ultérieur ne réattribue pas le média.
- Photos et vidéos partagent la galerie personnelle live. Les vidéos sont
  limitées côté client à 100 Mo et utilisent un poster Cloudinary (`so_0`).

## Fichiers importants

- `www/index.html`, `www/styles.css` — login, choix du prénom, dashboard,
  affectations, état GPS, PV, galerie et modals.
- `www/app.js` — cycle de vie, auth, outbox, GPS v2, PV et médias.
- `www/firebase-config.js` — configuration publique Firebase/Cloudinary,
  `AUTH_EMAIL` et roster `CREW` (Thomas n'en fait plus partie).
- `www/faces.js`, `www/icons/`, `www/manifest.json` — visages et PWA.
- `native/AfricaMediaPlugin.java`, `native/MainActivity.java`,
  `native/AndroidManifest.xml` — couche Android versionnée.
- `build-android.sh` — fixe actuellement Android `versionCode 2` /
  `versionName 2.1.0`, injecte le natif, synchronise Capacitor et génère
  `android/app/build/outputs/apk/debug/app-debug.apk`. Incrémenter le code à
  chaque APK publiée pour permettre la mise à jour par-dessus l'ancienne.
- `firestore.rules` — compatibilité v1 + validation stricte v2.
- `README.md` — configuration, publication des règles, build et distribution,
  avec l'URL GitHub Releases stable de téléchargement de la dernière APK.

Ne jamais versionner un mot de passe, un token Firebase CLI, un compte de
service, `node_modules/`, un APK ou un secret Cloudinary.
