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
- **Backend** : Firebase Firestore (positions, PV, méta-photos) +
  **Cloudinary** (fichiers photos, gratuit sans carte). Aucun serveur à gérer.

## Étape 1 — Firebase (À FAIRE PAR GAL, une seule fois, ~5 min)

1. Va sur <https://console.firebase.google.com> → **Ajouter un projet** →
   nomme-le `expedition-afrique` → désactive Google Analytics (inutile) →
   crée.
2. **Firestore** : cherche *Firestore* → *Créer une base* → mode
   **production** → région `europe-west`. Puis onglet *Règles* → colle le
   contenu de `firestore.rules` → *Publier*.
3. **Authentification** : cherche *Authentication* → *Commencer* →
   *Sign-in method* → active **Anonyme**.
4. **Clés** : ⚙️ *Paramètres du projet* → *Vos applications* → icône **Web**
   `</>` → copie l'objet `firebaseConfig` dans **`www/firebase-config.js`**.

> **Pas de Firebase Storage** : sur les projets récents il exige une carte
> bancaire (plan Blaze). On ne l'utilise donc PAS. Les fichiers photo vont
> sur Cloudinary (gratuit, sans carte) — voir l'étape suivante. Firebase ne
> garde que les positions, PV et méta-photos (tout ça reste gratuit).

## Étape 1bis — Cloudinary pour les fichiers photo (gratuit, SANS carte)

1. Crée un compte sur <https://cloudinary.com> (juste un e-mail, aucune carte).
2. Sur le tableau de bord, note ton **Cloud name**.
3. *Settings ⚙️ → Upload → Upload presets → Add upload preset* → mets
   **Signing Mode: Unsigned** → Save. Note le **nom du preset**.
4. Colle `cloudName` et `preset` dans **`www/firebase-config.js`** (objet
   `CLOUDINARY`).

Rien de secret : un preset non signé est conçu pour l'envoi depuis le client.

Ces clés Firebase/Cloudinary ne sont pas secrètes ; la sécurité vient des
règles Firestore et du preset restreint.

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
- [x] Règles de sécurité Firestore
- [x] Photos via Cloudinary (pas de Firebase Storage → pas de carte)
- [x] Projet Firebase : Firestore + Auth Anonyme + clés (africatrip-eea1a)
- [x] Cloudinary : cloudName `xlnsbhju` + preset unsigned `expedition`
- [ ] Plugin natif `AfricaMedia` (GPS des photos) + build APK (Basement)
- [ ] Lecture live côté site
