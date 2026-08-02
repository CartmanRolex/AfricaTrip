# App équipage — Expédition Afrique

Application Android/PWA de l'équipage. Chaque personne choisit son identité et
son contexte de déplacement, puis l'application enregistre sa propre trace GPS
pendant qu'elle reste ouverte. Les choix disponibles sont :

- **Hugodouard** ;
- **Paul Pot** ;
- **À pied / autre** ;
- **Pause** — aucun point GPS n'est enregistré.

Il n'y a pas de balise dédiée aux voitures. Le site public reconstruit leur
trajet à partir des points des occupants qui avaient sélectionné la voiture au
moment de chaque capture. Les trajets personnels restent séparés.

Les fichiers photo/vidéo sont hébergés par Cloudinary ; Firestore contient les
affectations, les traces, les derniers points, les PV et les métadonnées des
médias.

## Firebase déjà configuré

Projet : `africatrip-eea1a`.

L'application utilise Firebase Authentication **Email/Password** avec un seul
compte partagé : `equipage@expedition-afrique.app`. Le mot de passe n'est pas
dans le dépôt et ne doit jamais y être ajouté. Firebase garde la session après
la première connexion.

Si le projet doit être recréé ou réparé dans la console Firebase :

1. Active Firestore en mode production.
2. Dans Authentication → Sign-in method, active **Email/Password**.
3. Dans Authentication → Users, crée exactement
   `equipage@expedition-afrique.app` avec le mot de passe partagé hors dépôt.
4. N'ajoute aucun parcours d'inscription dans l'application et ne publie pas ce
   mot de passe.
5. Vérifie que `www/firebase-config.js` vise le projet
   `africatrip-eea1a` et que `AUTH_EMAIL` correspond à l'utilisateur créé.

Les clés du SDK Web Firebase ne sont pas des secrets. La protection des
écritures vient de `app/firestore.rules`, qui exige ce compte exact.

## Publier les règles Firestore

La configuration CLI est versionnée à la racine :

- `.firebaserc` sélectionne `africatrip-eea1a` ;
- `firebase.json` pointe vers `app/firestore.rules`.

Depuis la racine du dépôt :

```bash
firebase login
firebase use africatrip-eea1a
firebase deploy --only firestore:rules
```

Publier les règles **avant** une nouvelle version de l'application. Contrôler
ensuite dans la console Firebase que la version active contient les chemins
`trips/{tripId}/assignmentEvents`, `trackChunks` et `latest`. Ne jamais mettre
un token de connexion Firebase CLI ou un compte de service dans le dépôt.

Les lectures nécessaires à la carte sont publiques ; toutes les écritures sont
réservées au compte partagé. Les collections v1 `positions` et `tracks` restent
acceptées uniquement pour les anciennes versions et les données historiques.
L'application v2 n'y écrit plus.

## Données v2

Le voyage actif porte l'identifiant `africa-trip-01` :

```text
trips/africa-trip-01/
├── assignmentEvents/{assignmentId}  choix immuable personne/voiture/mode
├── trackChunks/{chunkId}            points personnels groupés et idempotents
└── latest/{personId}                dernier point exact de la personne
```

Chaque point contient notamment `personId`, `displayName`, `vehicleId`, `mode`,
`assignmentId`, `sessionId`, `deviceId`, `capturedAt`, `accuracyM`, `speedMps`,
`headingDeg`, `lat` et `lng`.

Un chunk correspond à une personne, une session, une affectation et une fenêtre
de deux heures. Les identifiants mis en file restent stables pendant les
retries : une nouvelle tentative n'ajoute pas de doublon. `latest` ne recule
jamais vers un point plus ancien.

La position est d'abord stockée dans une outbox locale IndexedDB, avec secours
`localStorage`. Elle n'est supprimée de la file qu'après une transaction
Firestore réussie. Hors ligne, la file est conservée et réessayée en FIFO avec
un backoff. Le suivi envoie au maximum un point par minute en mouvement et un
rappel toutes les cinq minutes à l'arrêt ; un fix moins précis que 250 m est
ignoré.

Autres collections :

- `crew/{nom}` : PV live ;
- `photos/{id}` : URL Cloudinary, lieu et contexte v2 de la personne au moment
  de l'ajout (`tripId`, `personId`, `vehicleIdAtCapture`, `mode`,
  `assignmentId`, `capturedAt`, `locationSource`).

## Cloudinary

Configuration dans `www/firebase-config.js` : cloud name `xlnsbhju`, preset
non signé `expedition`.

Le preset doit autoriser les images et les vidéos. Il est public par nature ;
ne jamais embarquer le secret API Cloudinary. Firebase Storage n'est pas
utilisé.

- Images : GPS EXIF natif sur Android, `exifr` dans la PWA.
- Vidéos : atome de localisation QuickTime lisible par le plugin Android ; pas
  par le fallback navigateur.
- Média sans GPS : carte Leaflet manuelle, immédiatement ou plus tard depuis le
  détail du média.
- Taille vidéo maximale côté client : 100 Mo.

## Construire l'APK Android

Prérequis : Node 20, JDK 17 et Android SDK avec la plateforme/build-tools 34.
Le script utilise l'environnement Conda `androidbuild` et `$HOME/android-sdk`
par défaut ; ils peuvent être remplacés via les variables documentées dans le
script.

Depuis la racine :

```bash
bash app/build-android.sh
```

Le script installe les dépendances si nécessaire, crée/synchronise le projet
Capacitor, injecte les fichiers Java de `app/native/`, puis lance Gradle.
Résultat :

```text
app/android/app/build/outputs/apk/debug/app-debug.apk
```

L'APK debug peut être installé directement sur Android. Après une modification
de `app/www/` ou `app/native/`, reconstruire puis réinstaller l'APK : une app
déjà installée ne récupère pas automatiquement ces fichiers.

## PWA iPhone

Le même `www/` est installable depuis Safari avec « Partager » → « Sur l'écran
d'accueil ». Il n'y a pas d'app iOS native. Le GPS de trajet utilise
`navigator.geolocation`; les médias passent par le sélecteur de fichiers et
`exifr`.

## Vérifications avant distribution

1. Les règles v2 sont publiées sur `africatrip-eea1a`.
2. Une connexion avec le mot de passe partagé ouvre le dashboard.
3. Une personne sans choix mémorisé démarre en Pause.
4. Changer Hugodouard ↔ Paul Pot ↔ À pied crée une nouvelle affectation et un
   nouveau point correctement étiqueté ; Pause arrête le watcher.
5. Couper le réseau, capturer un point, puis se reconnecter vide l'outbox sans
   doublon.
6. Une photo sans GPS peut être envoyée puis localisée depuis sa fiche.
7. Le site affiche la trace réelle de la bonne personne/voiture et zoome sur le
   dernier point valide.

## État

- [x] Application Android et PWA.
- [x] Auth Email/Password partagée.
- [x] Affectations persistantes et suivi GPS v2 par personne/voiture.
- [x] Outbox hors ligne idempotente.
- [x] Photos/vidéos Cloudinary enrichies et lieu modifiable après envoi.
- [x] Règles Firestore v2 et configuration de déploiement CLI.
- [x] Lecture publique Prévu/Réel/Comparer sur le site.
