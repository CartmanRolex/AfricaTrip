#!/usr/bin/env bash
# Construit l'APK debug de façon reproductible depuis ce dépôt.
# Prérequis (une fois, sur la machine de build) : un env avec Node 20 + JDK 17
# et le SDK Android (voir README étape 2). Puis :  bash app/build-android.sh
set -e
cd "$(dirname "$0")"

# outils (adapter si besoin)
export PATH="${ANDROIDBUILD_BIN:-$HOME/miniconda3/envs/androidbuild/bin}:$PATH"
export JAVA_HOME="${JAVA_HOME:-$HOME/miniconda3/envs/androidbuild}"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/android-sdk}"
export CAPACITOR_ANDROID_STUDIO_PATH=/bin/true

[ -d node_modules ] || npm install
[ -d android ] || npx cap add android

# Identité de mise à jour Android. Garder versionCode strictement croissant :
# l'APK publiée peut ainsi remplacer la v2.0.0 (qui portait encore code 1).
APP_VERSION_CODE=5
APP_VERSION_NAME=2.4.0
sed -i -E "s/versionCode [0-9]+/versionCode ${APP_VERSION_CODE}/" android/app/build.gradle
sed -i -E "s/versionName \"[^\"]+\"/versionName \"${APP_VERSION_NAME}\"/" android/app/build.gradle

# injecte nos fichiers natifs (versionnés dans app/native/) dans le projet généré
PKG=android/app/src/main/java/com/expedition/afrique
cp native/AfricaMediaPlugin.java "$PKG/"
cp native/VideoTranscoder.java    "$PKG/"
cp native/MainActivity.java       "$PKG/"
cp native/AndroidManifest.xml     android/app/src/main/AndroidManifest.xml

# dépendance pour lire l'EXIF (androidx.exifinterface), une seule fois
grep -q "exifinterface" android/app/build.gradle || \
  sed -i '/^dependencies {/a\    implementation "androidx.exifinterface:exifinterface:1.3.7"' android/app/build.gradle

npx cap sync android
cd android
./gradlew assembleDebug
echo
echo "APK  ->  app/android/app/build/outputs/apk/debug/app-debug.apk"
