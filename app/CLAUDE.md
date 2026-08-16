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
   Le choix est conservé par cookie + `localStorage`. **Sans choix mémorisé,
   le défaut est la voiture du roster** (`defaultAssignmentFor()`, d'après
   `CREW`) ; un observateur ou un prénom inconnu reste en Pause. Le défaut
   précédent était Pause pour tout le monde : les points et médias d'un
   équipier qui n'avait rien choisi partaient en `car:"obs"`, hors voiture, et
   son trajet ne rejoignait jamais celui de sa voiture sur le site.
   Conséquence assumée : le partage GPS démarre dès l'ouverture de l'app pour
   quelqu'un du roster ; **Pause** reste à un tap.
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
- **UN CHANGEMENT DE PERSONNE OU DE VOITURE N'EST ACQUIS QU'APRÈS 30 s**
  (`REGLAGE_STABLE_MS`, `reglageEnAttente()`, `assignmentChanged()`).
  Changer l'un ou l'autre remet le compteur de cadence à zéro et redémarre le
  GPS avec `maximumAge: 0` : le tout premier fix arrive en une ou deux secondes
  et était écrit immédiatement sous le nouveau réglage. Faire défiler le
  sélecteur écrivait donc un point par prénom traversé — le 10/08 un seul
  téléphone a signé Gal, Hugo, Hugo et Paul en onze secondes, et le site a
  placé Hugo dans une voiture où il n'était pas, pendant deux jours.
  Chaque changement REPOUSSE l'échéance, donc traverser cinq prénoms ne fait
  pas cinq réglages acquis : il n'y en a qu'un, le dernier, et seulement s'il
  tient. Un réglage qu'on traverse ne tient pas trente secondes, un réglage
  qu'on choisit oui. Le trajet ne perd rien — c'est une demi-seconde de route
  sur un point par minute — et la carte affiche « Choix en cours de
  confirmation » pendant l'attente plutôt que de rester figée.
  `assignmentChanged()` est le point de passage UNIQUE des deux chemins
  (démarrage de session et bouton de voiture), c'est pourquoi la règle y tient
  en une ligne. Vérifié en rejouant la séquence réelle du 10/08 :
  quatre points fantômes deviennent zéro, un changement délibéré reste
  enregistré (premier point à +34 s).
  Côté site, `excluded_points` de `site-overrides.json` désavoue les points
  déjà écrits par ce défaut ; c'est du rattrapage, la correction est ici.
- **LA CARTE DE CHOIX DU LIEU S'OUVRE LÀ OÙ EST LA VOITURE** (`POS_KEY`,
  `LIEU_KEY`, `VUE_LARGE`, `positionVoiture()`). Elle s'ouvrait sur
  `[16.5, -14]` au zoom 4 — le Sahara : sur un fond sombre, une étendue sans
  route ni label donne un rectangle noir où l'on ne peut rien situer, donc
  impossible de savoir où glisser l'épingle. Et le seul repli mémorisé,
  `lastUploadLocation`, était une variable EN MÉMOIRE, perdue à chaque
  redémarrage : le repli servait donc presque toujours.
  L'ordre est maintenant : GPS du média → dernière position enregistrée par ce
  téléphone → dernier lieu choisi à la main (les deux gardés en
  `localStorage`, donc ils survivent au redémarrage et marchent hors ligne) →
  dernière position connue d'un équipier de la MÊME voiture (une seule lecture
  Firestore, uniquement quand le téléphone ne sait rien — le cas du passager
  qui ne lance jamais le GPS) → et seulement alors une vue large.
  La lecture réseau ne bloque jamais : la carte s'ouvre tout de suite avec ce
  qu'on a, et ne se recadre que si la réponse arrive **et** que l'utilisateur
  n'a pas déjà bougé la carte lui-même.
  `VUE_LARGE` = `[36, -6]` zoom 4 (Gibraltar, côtes d'Espagne et du Maroc),
  choisi en MESURANT le poids réel des tuiles CARTO de plusieurs candidats :
  27 % de contenu de plus que l'ancien défaut saharien. Un premier essai à
  `[25, -8]` zoom 3 tombait sur l'Atlantique et était **pire** que ce qu'il
  remplaçait — ne pas rechoisir ce point sans remesurer.
  `voitureCourante` est tenue à jour par `assignmentChanged()`, le même point
  de passage unique que la règle des 30 s.
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

## Jauges PV / Mana / Éveil

Trois curseurs 0-10 pilotés par le MÊME mécanisme (`STATS` + une seule boucle
dans `initStats()`), chacun écrivant son champ dans `crew/{prénom}` en
`{merge:true}` — le site les relit en direct. Une boucle plutôt que trois copies,
c'est ce qui garantit qu'elles se comportent pareil.

**Les jauges sont gardées sur le téléphone AVANT d'être envoyées**
(`crew-stats-<prénom>` en localStorage). Deux défauts réels que ça corrige : les
curseurs affichaient **5** en attendant la réponse du serveur, si bien qu'un
quota épuisé ou un réseau lent laissait ce 5 en place avec l'aplomb d'une vraie
valeur — c'est la « remise à zéro » constatée en rouvrant l'app ; et un
enregistrement raté n'était ni conservé ni réessayé, donc la valeur était perdue
puis écrasée par l'ancienne au rechargement. À l'ouverture on affiche
immédiatement ce qu'on sait, puis on réconcilie : **une valeur non encore
envoyée bat celle du serveur**, sinon on écraserait le réglage de l'équipier.
Les restes en attente repartent au lancement suivant. Les points GPS avaient
leur file durable depuis toujours ; les jauges n'avaient rien.

**Une minuterie par jauge** (`statsTimer_<clé>`) : une seule minuterie partagée
faisait qu'en bougeant le Mana on annulait l'enregistrement des PV réglés une
demi-seconde plus tôt. `cleanupDashboard()` les annule TOUTES, sinon un curseur
bougé juste avant un changement de personne écrirait sous l'identité suivante.

Les règles Firestore de `crew` acceptent n'importe quel champ : ajouter une
jauge ne demande aucun déploiement de règles.

## Médias

- Les fichiers vont sur Cloudinary via le preset non signé `expedition` ; seul
  le `secure_url` et les métadonnées vont dans Firestore. Firebase Storage n'est
  pas utilisé.
- **Une photo est allégée sur le téléphone, avant de partir.** `compressImage()`
  ré-encode en JPEG qualité 0.85 **à la résolution d'origine** : on ne
  redimensionne pas, on ne fait que défaire la qualité quasi maximale qu'écrit
  l'appareil. Mesuré sur un original 4032x3024 : 3,6 Mo -> 1,6 Mo, soit 55 % de
  moins pour la même image. C'est le trajet téléphone -> Cloudinary qu'on
  raccourcit, en données mobiles et sur un réseau instable ; les transformations
  Cloudinary (`w_1400,c_limit,q_auto,f_auto`, vignettes) sont un sujet distinct
  et complémentaire — elles allègent ce que le VISITEUR télécharge, une fois le
  fichier déjà stocké. Deux garde-fous : le résultat n'est gardé que s'il est
  réellement plus léger (une capture déjà optimisée repart intacte), et toute
  erreur renvoie l'original. Le canvas efface l'EXIF, sans conséquence : GPS et
  date sont lus AVANT (ExifInterface en natif, exifr en navigateur) et voyagent
  dans des champs à part — mais `imageOrientation: "from-image"` est
  obligatoire, sinon les photos prises en portrait arrivent couchées.
- **Une vidéo est allégée sur le téléphone, elle aussi — au DÉBIT seulement.**
  `VideoTranscoder.lighten()` (`native/VideoTranscoder.java`, appelé depuis
  `readVideo()`) ré-encode en H.264 à **résolution, durée et cadence
  identiques** : un téléphone filme à ~50 Mb/s en 4K et ~17 Mb/s en 1080p, très
  au-delà de ce que l'image exige, et c'est ce seul excès qu'on retire. Cible :
  0.11 bit/pixel/image (~6,8 Mb/s en 1080p30), plafonnée à 16 Mb/s. Le son est
  recopié tel quel — il pèse peu, le ré-encoder ne ferait que le dégrader.
  Trois garde-fous, un ré-encodage étant une perte définitive : en dessous de
  25 Mo on ne touche à rien, un gain attendu inférieur à 25 % fait renoncer, et
  toute erreur renvoie l'original. La rotation est reportée sur le conteneur
  (`setOrientationHint`) sinon un clip filmé en portrait ressort couché.
  Ne pas tenter ffmpeg.wasm côté JS : trop lent et trop gourmand en mémoire sur
  mobile.
- **L'image passe du décodeur à l'encodeur par une Surface**, jamais par la
  mémoire Java. C'est ce qui rend le ré-encodage tenable en 4K sur un téléphone
  modeste, et ça évite tout le folklore des formats de couleur YUV.
- **`picked()` fait son travail sur un thread dédié.** Ce callback arrive sur le
  thread principal et l'allègement d'une vidéo dure des secondes : y rester
  ferait tuer l'app pour ANR. `call.resolve()` depuis un autre thread est sûr.
- `MAX_VIDEO_BYTES` (100 Mo côté JS) ne compresse pas, il REFUSE — c'est le
  plafond de l'upload non signé Cloudinary, et le filet quand l'allègement a
  renoncé. Il reste seul en vigueur dans le navigateur, où il n'y a pas de
  plugin natif. Le clip est encore chargé ENTIÈREMENT en mémoire par la WebView
  pour être envoyé : un envoi natif en flux supprimerait ce plafond, mais c'est
  un autre chantier.
- **Un fichier de plus de 6 Mo part en TRANCHES** (`sendInChunks()`). En un seul
  bloc, une coupure à 90 % perd tout et il faut tout recommencer : sur un réseau
  instable, un gros clip ne passe alors jamais. Constaté en itinérance, un envoi
  de 22 Mo mourait sur `Failed to fetch`. Découpé, une coupure ne coûte que la
  tranche en cours ; chacune est retentée jusqu'à `CHUNK_TRIES` fois avec une
  attente croissante, et les tranches déjà acceptées sont acquises. Cloudinary
  recolle grâce à `X-Unique-Upload-Id` (identique pour tout le fichier) +
  `Content-Range` ; la dernière réponse porte le `secure_url`. `CHUNK_BYTES` ne
  peut pas descendre sous 5 Mo, Cloudinary refuse les tranches plus petites.
  Un refus explicite (HTTP 4xx) porte `err.refused` et n'est jamais retenté —
  insister ne changerait rien et masquerait le vrai message.
- **Ceci couvre aussi le passage en arrière-plan**, la cause la plus probable
  des envois morts : Android suspend la WebView dès qu'on bascule sur une autre
  app, et un gros blob en mémoire fait du processus une cible de choix pour le
  tueur de mémoire. La boucle de reprise repart de la dernière tranche acceptée
  au retour au premier plan. Si le processus est vraiment TUÉ, tout est perdu :
  seul un service de premier plan (notification « envoi en cours ») l'éviterait,
  et il reste à faire.
- **La barre d'envoi montre l'envoi tel qu'il est fait** (`upBar`, `.upbar*`
  dans `styles.css`). Ses repères ne décorent pas : ils tombent sur les
  frontières des tranches, donc ils donnent à voir ce qui est déjà à l'abri
  d'une coupure. Un fichier envoyé d'un bloc n'en a aucun. Une reprise vire à
  l'ambre plutôt que de reculer en silence — un recul muet est ce qui fait
  croire à un blocage. Vert puis effacement à la fin ; toute erreur appelle
  `upBar.hide()`, une barre figée à l'écran serait pire que pas de barre.
- **`postSlice()` utilise XHR et non `fetch()`.** C'est la seule raison :
  `fetch` ne sait pas dire où en est un envoi (`upload.onprogress`), et sans
  cela la barre ne pourrait qu'inventer sa progression. Le prix est que la
  fonction renvoie le corps BRUT (`responseText`), d'où le `JSON.parse` côté
  appelant. `xhr.onerror` reprend volontairement le libellé « Failed to
  fetch » pour que les rapports d'erreur déjà connus restent comparables.
- **L'écriture du média est IDEMPOTENTE.** L'identifiant du document Firestore
  est calculé (`personId-capturedAtMs-taille`) au lieu d'être tiré au hasard par
  `addDoc` : un envoi interrompu puis retenté peut avoir abouti côté Cloudinary
  sans que l'app l'apprenne, et le second essai créait alors un document de plus
  — deux vignettes superposées sur la carte, constaté trois fois sur les données
  réelles. Avec `setDoc`, le retour écrase au lieu d'ajouter. La taille entre
  dans la clé pour qu'une rafale (deux photos dans la même seconde) garde des
  identifiants distincts, et la clé est filtrée sur `[A-Za-z0-9_-]`.
- **Diagnostiquer un échec d'envoi.** Le chemin vidéo natif comporte DEUX
  `fetch` : relire le fichier copié en cache, puis l'envoyer à Cloudinary. Les
  deux échouaient avec le même « Failed to fetch », impossible à départager.
  `readLocalVideo()` essaie maintenant les formes d'URL connues
  (`convertFileSrc`, schéma de la WebView, chemin brut) et nomme celle qui a
  échoué ; l'envoi Cloudinary rapporte séparément la taille et, en cas de refus
  HTTP, le message de Cloudinary. Le preset non signé `expedition` et
  l'endpoint `/video/upload` ont été vérifiés directement : un envoi de test y
  passe en HTTP 200, donc un échec vient d'ailleurs.
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
- `build-android.sh` — porte `APP_VERSION_CODE` / `APP_VERSION_NAME` (source
  UNIQUE du numéro de version), injecte le natif, synchronise Capacitor et
  génère `android/app/build/outputs/apk/debug/app-debug.apk`. Incrémenter le
  code à chaque APK publiée pour permettre la mise à jour par-dessus
  l'ancienne. Version courante : `versionCode 10` / `2.9.0`.
- `release.sh` — publie l'APK. **NE JAMAIS publier une release à la main.**
  L'équipage télécharge par un lien permanent
  (`releases/latest/download/expedition-afrique.apk`) que GitHub résout par NOM
  DE FICHIER EXACT : une release publiée sous `expedition-afrique-2.9.0.apk` —
  un nom qui paraît plus clair — casse ce lien pour tout le monde en silence.
  La release existe, elle s'affiche, seul le lien meurt. C'est arrivé avec la
  2.9.0. Le nom du fichier n'est donc plus une décision : il est écrit une fois
  dans le script. Celui-ci refuse en plus de publier une APK qui ne contient
  pas le `app/www/app.js` du dépôt (sinon on publie l'ancienne app sous le
  nouveau numéro), puis **vérifie que le lien permanent sert bien cette APK**,
  en comparant sa taille. C'est le seul contrôle qui compte : tout le reste
  peut être vert et ce lien mort.
- `firestore.rules` — compatibilité v1 + validation stricte v2.
- `README.md` — configuration, publication des règles, build et distribution,
  avec l'URL GitHub Releases stable de téléchargement de la dernière APK.

Ne jamais versionner un mot de passe, un token Firebase CLI, un compte de
service, `node_modules/`, un APK ou un secret Cloudinary.
