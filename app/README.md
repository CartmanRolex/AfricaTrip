# App équipage — Expédition Afrique

Petite appli Android pour l'équipage : partage de position (quand l'appli est
ouverte), édition de ses PV/XP, et **upload de photos en gardant leur
localisation** (ce que le navigateur ne sait plus faire sur Android depuis
avril 2026). Les données vont dans Firebase ; le site les lit et les met sur
la carte.

- **UI** : `www/` (web simple, thème désert), emballée en app native par
  **Capacitor** (seul le natif peut lire le GPS des photos via la permission
  `ACCESS_MEDIA_LOCATION`).
- **Login** : aucun. On choisit son prénom une fois ; Firebase **Anonymous**
  (invisible) connecte l'appli pour que les règles acceptent l'écriture.
- **Backend** : Firebase Firestore (positions, PV, méta-photos) + Storage
  (fichiers photos). Aucun serveur à gérer.

## Étape 1 — Firebase (À FAIRE PAR GAL, une seule fois, ~5 min)

1. Va sur <https://console.firebase.google.com> → **Ajouter un projet** →
   nomme-le `expedition-afrique` → désactive Google Analytics (inutile) →
   crée.
2. **Firestore** : menu *Build → Firestore Database* → *Créer une base* →
   mode **production** → région `europe-west`. Puis onglet *Règles* → colle
   le contenu de `firestore.rules` → *Publier*.
3. **Storage** : *Build → Storage* → *Commencer* → région `europe-west` →
   onglet *Règles* → colle `storage.rules` → *Publier*.
4. **Authentification** : *Build → Authentication* → *Commencer* → active
   **Anonyme** (Sign-in method → Anonyme → Activer).
5. **Clés** : ⚙️ *Paramètres du projet* → section *Vos applications* →
   icône **Web** `</>` → enregistre l'app (nom au choix) → copie l'objet
   `firebaseConfig`. Colle ses valeurs dans **`www/firebase-config.js`**
   (apiKey, authDomain, projectId, storageBucket, appId).

C'est tout côté Firebase. Ces clés ne sont pas secrètes (le SDK web les
expose) ; la sécurité vient des règles ci-dessus.

## Étape 2 — Construire l'APK (fait par Claude sur le serveur Basement)

Le PC de Gal n'a aucun outil Android ; on compile sur Basement (Linux,
headless). Grandes lignes (Claude s'en occupe) :

```bash
# env de build : Node + JDK 17 + Android command-line tools
conda create -y -n androidbuild nodejs=20 openjdk=17
# ... sdkmanager: platform-tools, platforms;android-34, build-tools;34.0.0
npm create @capacitor/app  # ou init dans app/
npm i @capacitor/core @capacitor/cli @capacitor/geolocation
npx cap add android
# + un petit plugin natif "AfricaMedia" (Kotlin) qui ouvre le sélecteur de
#   photos, demande ACCESS_MEDIA_LOCATION, lit le GPS EXIF (setRequireOriginal
#   + ExifInterface) et renvoie {blob, lat, lng, date} au JS.
cd android && ./gradlew assembleDebug   # -> app-debug.apk
```

L'APK signé en debug s'installe directement (pas besoin du Play Store).

## Étape 3 — Distribuer

- **Android** : envoie `app-debug.apk` aux potes (WhatsApp/mail). Ils ouvrent
  le fichier → « Autoriser cette source » → Installer. Une fois.
- **iPhone** : pas concerné par le bug de localisation → ils pourront ouvrir
  la version web (PWA) si besoin ; à voir plus tard.

## Étape 4 — Le site lit les données live

Le site (`src/template.html`) ajoutera un petit lecteur Firebase (client, en
lecture seule) : marqueurs de position en temps réel, tracé réellement
parcouru, PV live, et photos qui apparaissent instantanément (plus besoin de
`sync.bat`). Le Google Sheet reste pour l'éditorial (route, étapes, danger).

## État

- [x] UI de l'app (`www/`) + logique Firebase + fallback navigateur pour test
- [x] Règles de sécurité Firestore/Storage
- [ ] Projet Firebase créé + clés collées (étape 1 — **Gal**)
- [ ] Plugin natif `AfricaMedia` (GPS des photos) + build APK (Basement)
- [ ] Lecture live côté site
