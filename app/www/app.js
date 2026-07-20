// Expédition Afrique — appli de l'équipage.
// Choix du prénom (une fois) -> partage de position + PV/XP + upload photos.
// Tout part dans Firebase ; le site lit ces données et les met sur la carte.
//
// Firebase est chargé PARESSEUSEMENT (import dynamique au 1er besoin) : ainsi
// l'écran de choix du prénom s'affiche toujours, même hors-ligne ou si le CDN
// tarde. Seul l'import LOCAL ci-dessous est au niveau module.

import { FIREBASE_CONFIG, CLOUDINARY, CREW } from "./firebase-config.js";

const $ = id => document.getElementById(id);
const CAR_COLOR = { 1: "#E8924A", 2: "#4FB7B3", obs: "#8E8066" };
const V = "10.12.2", CDN = n => `https://www.gstatic.com/firebasejs/${V}/firebase-${n}.js`;
let me = localStorage.getItem("crew-me");

// dans l'APK (Capacitor), on utilise les plugins natifs ; dans un navigateur
// (test/PWA), on retombe sur les API web (navigator.geolocation, <input file>)
const CAP = window.Capacitor;
const native = !!(CAP && CAP.isNativePlatform && CAP.isNativePlatform());
// accès à un plugin natif — selon la version de Capacitor c'est
// Capacitor.registerPlugin(...) OU Capacitor.Plugins.X ; on gère les deux
function plugin(name) {
  if (CAP && typeof CAP.registerPlugin === "function") return CAP.registerPlugin(name);
  if (CAP && CAP.Plugins && CAP.Plugins[name]) return CAP.Plugins[name];
  return null;
}
function b64toBlob(b64, type = "image/jpeg") {
  const bin = atob(b64), arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type });
}

// ---- Firebase à la demande -----------------------------------------------
let _fb = null;
async function fb() {
  if (_fb) return _fb;
  const [a, au, fs] = await Promise.all([
    import(CDN("app")), import(CDN("auth")), import(CDN("firestore"))]);
  const app = a.initializeApp(FIREBASE_CONFIG);
  au.signInAnonymously(au.getAuth(app)).catch(e => console.warn("auth:", e));
  _fb = { db: fs.getFirestore(app),
          doc: fs.doc, setDoc: fs.setDoc, addDoc: fs.addDoc,
          collection: fs.collection, ts: fs.serverTimestamp };
  return _fb;
}

// ---- écran 1 : choix du prénom -------------------------------------------
function renderPick() {
  const grid = $("crew");
  grid.innerHTML = "";
  for (const [name, car] of Object.entries(CREW)) {
    const b = document.createElement("button");
    b.innerHTML = `<span class="car-dot" style="background:${CAR_COLOR[car]}"></span>${name}`;
    b.onclick = () => { me = name; localStorage.setItem("crew-me", name); start(); };
    grid.appendChild(b);
  }
}

// ---- dashboard ------------------------------------------------------------
function start() {
  $("pick").classList.add("hidden");
  $("dash").classList.remove("hidden");
  $("me-name").textContent = me;
  const car = CREW[me];
  $("me-car").textContent = car === 1 ? "🚗 Hugodouard"
    : car === 2 ? "🚙 Paul Pot" : "🛰️ Observateur";
  $("switch").onclick = () => {
    localStorage.removeItem("crew-me"); me = null;
    $("dash").classList.add("hidden"); $("pick").classList.remove("hidden");
  };
  initPosition();
  initStats();
  initPhotos();
}

// ---- position (uniquement quand l'appli est ouverte) ----------------------
function initPosition() {
  let watchId = null, lastAt = 0, lastPt = null;

  const send = async (lat, lng) => {
    try {
      const { db, doc, setDoc, addDoc, collection, ts } = await fb();
      await setDoc(doc(db, "positions", me),
        { name: me, car: CREW[me], lat, lng, at: ts() });
      await addDoc(collection(db, "tracks", me, "points"),
        { lat, lng, at: ts() });
      $("pos-status").innerHTML =
        `<span class="ok">position partagée</span> · ${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    } catch (e) { $("pos-status").innerHTML = `<span class="err">erreur: ${e.code || e}</span>`; }
  };

  const onPos = (lat, lng) => {
    const now = Date.now();
    const moved = !lastPt || dist(lastPt, [lat, lng]) > 25; // ~25 m
    if (now - lastAt < 20000 && !moved) return;             // ou 20 s
    lastAt = now; lastPt = [lat, lng];
    send(lat, lng);
  };

  const startWatch = async () => {
    if (watchId != null) return;
    $("pos-status").textContent = "en attente du GPS…";
    if (native) {                        // APK : plugin natif Geolocation
      const Geo = plugin("Geolocation");
      try { await Geo.requestPermissions(); } catch (_) {}
      watchId = await Geo.watchPosition({ enableHighAccuracy: true }, (pos, err) => {
        if (err || !pos) { $("pos-status").innerHTML = `<span class="err">GPS: ${(err && err.message) || "?"}</span>`; return; }
        onPos(pos.coords.latitude, pos.coords.longitude);
      });
    } else if (navigator.geolocation) {  // navigateur / PWA
      watchId = navigator.geolocation.watchPosition(
        p => onPos(p.coords.latitude, p.coords.longitude),
        e => { $("pos-status").innerHTML = `<span class="err">GPS refusé (${e.code})</span>`; },
        { enableHighAccuracy: true, maximumAge: 15000, timeout: 20000 });
    }
  };
  const stopWatch = () => {
    if (watchId != null) {
      if (native) plugin("Geolocation").clearWatch({ id: watchId });
      else navigator.geolocation.clearWatch(watchId);
    }
    watchId = null; $("pos-status").textContent = "partage en pause";
  };

  $("share").onchange = e => e.target.checked ? startWatch() : stopWatch();
  if ($("share").checked) startWatch();
}

function dist(a, b) { // mètres, approx équirectangulaire
  const k = Math.cos(a[0] * Math.PI / 180), R = 6371000, r = Math.PI / 180;
  const dx = (b[1] - a[1]) * k * r, dy = (b[0] - a[0]) * r;
  return Math.sqrt(dx * dx + dy * dy) * R;
}

// ---- PV / XP / compétence -------------------------------------------------
function initStats() {
  const pv = $("pv"), pvVal = $("pv-val");
  pv.oninput = () => pvVal.textContent = pv.value;
  $("save-stats").onclick = async () => {
    $("stats-status").textContent = "enregistrement…";
    try {
      const { db, doc, setDoc, ts } = await fb();
      await setDoc(doc(db, "crew", me), {
        name: me, car: CREW[me],
        pv: +pv.value, xp: +$("xp").value || 0,
        skill: $("skill").value.trim(), at: ts(),
      }, { merge: true });
      $("stats-status").innerHTML = `<span class="ok">enregistré ✓</span>`;
    } catch (e) { $("stats-status").innerHTML = `<span class="err">erreur: ${e.code || e}</span>`; }
  };
}

// ---- photos (localisation gardée) -----------------------------------------
function initPhotos() {
  $("add-photos").onclick = async () => {
    // natif (APK) : le plugin AfricaMedia lit le GPS EXIF grâce à
    // ACCESS_MEDIA_LOCATION. sinon (navigateur) : <input file> + EXIF en JS.
    if (native) {
      try {
        const { items } = await plugin("AfricaMedia").pickWithLocation();
        for (const it of (items || []))
          await uploadPhoto(b64toBlob(it.base64), it.lat ?? null, it.lng ?? null, it.date || null);
      } catch (e) { $("up-status").innerHTML = `<span class="err">erreur: ${e.message || e}</span>`; }
    } else {
      $("fallback-input").click();
    }
  };
  $("fallback-input").onchange = async e => {
    const exifr = await import("https://cdn.jsdelivr.net/npm/exifr@7.1.3/dist/full.esm.mjs");
    for (const f of e.target.files) {
      let lat = null, lng = null, date = null;
      try {
        const g = await exifr.gps(f);
        if (g) { lat = g.latitude; lng = g.longitude; }
        const d = await exifr.parse(f, ["DateTimeOriginal"]);
        if (d && d.DateTimeOriginal) date = d.DateTimeOriginal.toISOString().slice(0, 10);
      } catch (_) {}
      await uploadPhoto(f, lat, lng, date);
    }
    e.target.value = "";
  };
}

async function uploadPhoto(blob, lat, lng, date) {
  const st = $("up-status");
  st.textContent = "envoi…";
  try {
    // le FICHIER va sur Cloudinary (gratuit, sans carte) ; seules les
    // MÉTADONNÉES (nom, position, date, url) vont dans Firestore.
    const form = new FormData();
    form.append("file", blob);
    form.append("upload_preset", CLOUDINARY.preset);
    const res = await fetch(
      `https://api.cloudinary.com/v1_1/${CLOUDINARY.cloudName}/image/upload`,
      { method: "POST", body: form });
    if (!res.ok) throw new Error("upload " + res.status);
    const link = (await res.json()).secure_url;

    const { db, addDoc, collection, ts } = await fb();
    await addDoc(collection(db, "photos"), {
      name: me, car: CREW[me], url: link,
      lat: lat ?? null, lng: lng ?? null, gps: lat != null,
      date: date || new Date().toISOString().slice(0, 10), at: ts(),
    });
    const img = document.createElement("img");
    img.src = link; $("recent").prepend(img);
    st.innerHTML = lat != null
      ? `<span class="ok">photo ajoutée avec sa position ✓</span>`
      : `<span class="ok">photo ajoutée</span> (sans GPS → placée à la date)`;
  } catch (e) { st.innerHTML = `<span class="err">erreur: ${e.code || e}</span>`; }
}

// ---- go -------------------------------------------------------------------
if (me && CREW[me]) start(); else renderPick();
