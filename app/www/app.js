// Expédition Afrique — appli de l'équipage.
// Choix du prénom (une fois) -> partage de position + PV/XP + upload photos.
// Tout part dans Firebase ; le site lit ces données et les met sur la carte.
//
// Firebase est chargé PARESSEUSEMENT (import dynamique au 1er besoin) : ainsi
// l'écran de choix du prénom s'affiche toujours, même hors-ligne ou si le CDN
// tarde. Seul l'import LOCAL ci-dessous est au niveau module.

import { FIREBASE_CONFIG, CLOUDINARY, CREW, AUTH_EMAIL } from "./firebase-config.js";
import { FACES } from "./faces.js";

const $ = id => document.getElementById(id);
const CAR_COLOR = { 1: "#E8924A", 2: "#4FB7B3", obs: "#8E8066" };
const V = "10.12.2", CDN = n => `https://www.gstatic.com/firebasejs/${V}/firebase-${n}.js`;

// ---- perso mémorisé : COOKIE (fiable sur iPhone « écran d'accueil », où le
// localStorage d'une PWA peut être vidé) + miroir localStorage. On relit le
// cookie en priorité, localStorage en secours ; on ré-écrit à chaque ouverture
// pour repousser l'expiration (fenêtre glissante). --------------------------
const ME_KEY = "crew-me";
function saveMe(name) {
  try { localStorage.setItem(ME_KEY, name); } catch (_) {}
  document.cookie = `${ME_KEY}=${encodeURIComponent(name)}; Max-Age=${60 * 60 * 24 * 400}; Path=/; SameSite=Lax`;
}
function clearMe() {
  try { localStorage.removeItem(ME_KEY); } catch (_) {}
  document.cookie = `${ME_KEY}=; Max-Age=0; Path=/; SameSite=Lax`;
}
function loadMe() {
  const m = document.cookie.match(/(?:^|;\s*)crew-me=([^;]*)/);
  if (m) { try { return decodeURIComponent(m[1]); } catch (_) { return m[1]; } }
  try { return localStorage.getItem(ME_KEY); } catch (_) { return null; }
}
let me = loadMe();

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
  const auth = au.getAuth(app);
  _fb = { auth,
          signIn: pw => au.signInWithEmailAndPassword(auth, AUTH_EMAIL, pw),
          onAuth: cb => au.onAuthStateChanged(auth, cb),
          db: fs.getFirestore(app),
          doc: fs.doc, getDoc: fs.getDoc, setDoc: fs.setDoc,
          addDoc: fs.addDoc, deleteDoc: fs.deleteDoc,
          collection: fs.collection, query: fs.query, where: fs.where,
          onSnapshot: fs.onSnapshot, ts: fs.serverTimestamp };
  return _fb;
}

// ---- porte d'entrée : mot de passe partagé (une seule fois) ----------------
// L'équipage partage UN mot de passe (compte Firebase unique). Firebase garde
// la session, donc on ne le retape qu'au 1er lancement (ou nouveau tel). Le
// site, lui, lit tout en public : aucune de ces vérifs ne le concerne.
function requireAuth() {
  return new Promise(async resolve => {
    const { onAuth } = await fb();
    let shown = false;
    onAuth(user => {
      // on n'accepte QUE le compte équipage : une session laissée par une
      // ancienne version (anonyme, email nul) ne doit PAS ouvrir sans mot de
      // passe -> sinon on tombe sur le dashboard sans jamais le demander
      if (user && user.email === AUTH_EMAIL) resolve();
      else if (!shown) { shown = true; showLogin(); }
    });
  });
}
function showLogin() {
  $("pick").classList.add("hidden");
  $("dash").classList.add("hidden");
  $("login").classList.remove("hidden");
  const input = $("pw-input"), err = $("pw-err"), go = $("pw-go");
  input.focus();
  const submit = async () => {
    if (!input.value.trim()) return;
    go.disabled = true; err.textContent = "connexion…";
    try {
      const { signIn } = await fb();
      await signIn(input.value.trim());
      // succès -> onAuth(user) déclenche resolve() de requireAuth -> start()
    } catch (e) {
      err.innerHTML = `<span class="err">mot de passe incorrect</span>`;
      go.disabled = false; input.select();
    }
  };
  go.onclick = submit;
  input.onkeydown = e => { if (e.key === "Enter") submit(); };
}

// ---- écran 1 : choix du prénom -------------------------------------------
function renderPick() {
  const grid = $("crew");
  grid.innerHTML = "";
  for (const [name, car] of Object.entries(CREW)) {
    const b = document.createElement("button");
    b.innerHTML = `<span class="car-dot" style="background:${CAR_COLOR[car]}"></span>${name}`;
    b.onclick = () => { me = name; saveMe(name); start(); };
    grid.appendChild(b);
  }
}

// ---- dashboard ------------------------------------------------------------
async function start() {
  $("pick").classList.add("hidden");   // pas de flash de l'écran des prénoms
  await requireAuth();                 // mot de passe équipage (une fois)
  $("login").classList.add("hidden");
  $("dash").classList.remove("hidden");
  $("me-name").textContent = me;
  const face = FACES[me];
  if (face) $("me-face").src = face; else $("me-face").removeAttribute("src");
  const car = CREW[me];
  $("me-car").textContent = car === 1 ? "🚗 Hugodouard"
    : car === 2 ? "🚙 Paul Pot" : "🛰️ Observateur";
  $("switch").onclick = () => {
    clearMe(); me = null;
    $("dash").classList.add("hidden"); $("pick").classList.remove("hidden");
  };
  initPosition();
  initStats();
  initPhotos();
  watchMyPhotos();
}

// ---- position : TOUJOURS active tant que l'app est ouverte (pas de bouton) --
function initPosition() {
  let lastAt = 0, lastPt = null, sentAt = 0;
  const card = $("live-card");
  const setState = (cls, title, sub) => {
    card.className = "card live-card " + cls;
    $("pos-title").textContent = title;
    if (sub != null) $("pos-sub").innerHTML = sub;
  };
  // rafraîchit le "envoyée il y a X" toutes les 10 s
  setInterval(() => {
    if (!sentAt) return;
    const s = Math.round((Date.now() - sentAt) / 1000);
    const t = s < 60 ? `${s}s` : `${Math.round(s / 60)} min`;
    $("pos-sub").innerHTML = `envoyée il y a ${t} · ${lastPt[0].toFixed(4)}, ${lastPt[1].toFixed(4)}`;
  }, 10000);

  const send = async (lat, lng) => {
    try {
      const { db, doc, setDoc, addDoc, collection, ts } = await fb();
      await setDoc(doc(db, "positions", me),
        { name: me, car: CREW[me], lat, lng, at: ts() });
      await addDoc(collection(db, "tracks", me, "points"), { lat, lng, at: ts() });
      sentAt = Date.now();
      setState("live", "Position à jour ✓",
        `envoyée à l'instant · ${lat.toFixed(4)}, ${lng.toFixed(4)}`);
    } catch (e) { setState("err", "Envoi impossible", `${e.code || e}`); }
  };

  const onPos = (lat, lng) => {
    const now = Date.now();
    const moved = !lastPt || dist(lastPt, [lat, lng]) > 25; // ~25 m
    lastPt = [lat, lng];
    if (now - lastAt < 20000 && !moved) return;             // ou 20 s
    lastAt = now;
    send(lat, lng);
  };

  (async () => {
    setState("waiting", "Activation du GPS…",
      "ta position est partagée pendant que l'app est ouverte");
    if (native) {
      const Geo = plugin("Geolocation");
      try { await Geo.requestPermissions(); } catch (_) {}
      await Geo.watchPosition({ enableHighAccuracy: true }, (pos, err) => {
        if (err || !pos) return setState("err", "GPS indisponible", (err && err.message) || "autorise la localisation");
        onPos(pos.coords.latitude, pos.coords.longitude);
      });
    } else if (navigator.geolocation) {
      navigator.geolocation.watchPosition(
        p => onPos(p.coords.latitude, p.coords.longitude),
        e => setState("err", "GPS refusé", `autorise la localisation (${e.code})`),
        { enableHighAccuracy: true, maximumAge: 15000, timeout: 20000 });
    } else setState("err", "GPS non disponible", "");
  })();
}

function dist(a, b) { // mètres, approx équirectangulaire
  const k = Math.cos(a[0] * Math.PI / 180), R = 6371000, r = Math.PI / 180;
  const dx = (b[1] - a[1]) * k * r, dy = (b[0] - a[0]) * r;
  return Math.sqrt(dx * dx + dy * dy) * R;
}

// ---- PV / XP (sauvegarde automatique à chaque modification) ----------------
function initStats() {
  const pv = $("pv"), pvVal = $("pv-val");
  let t = null;
  pv.oninput = () => {
    pvVal.textContent = pv.value;
    clearTimeout(t);
    $("stats-status").textContent = "…";
    t = setTimeout(async () => {
      try {
        const { db, doc, setDoc, ts } = await fb();
        await setDoc(doc(db, "crew", me),
          { name: me, car: CREW[me], pv: +pv.value, at: ts() }, { merge: true });
        $("stats-status").innerHTML = `<span class="ok">enregistré ✓</span>`;
      } catch (e) { $("stats-status").innerHTML = `<span class="err">${e.code || e}</span>`; }
    }, 500);   // léger délai pour ne pas écrire à chaque cran du curseur
  };

  // charge mes PV déjà enregistrés
  (async () => {
    try {
      const { db, doc, getDoc } = await fb();
      const snap = await getDoc(doc(db, "crew", me));
      if (snap.exists() && snap.data().pv != null) {
        pv.value = snap.data().pv; pvVal.textContent = snap.data().pv;
        $("stats-status").textContent = "enregistré automatiquement";
      }
    } catch (_) {}
  })();
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
    // la grille "mes photos" se met à jour toute seule (onSnapshot)
    st.innerHTML = lat != null
      ? `<span class="ok">photo ajoutée avec sa position ✓</span>`
      : `<span class="ok">photo ajoutée</span> (sans GPS → placée à la date)`;
  } catch (e) { st.innerHTML = `<span class="err">erreur: ${e.code || e}</span>`; }
}

// ---- mes photos : grille live + suppression -------------------------------
async function watchMyPhotos() {
  const { db, collection, query, where, onSnapshot } = await fb();
  onSnapshot(query(collection(db, "photos"), where("name", "==", me)), snap => {
    const docs = [];
    snap.forEach(d => docs.push({ id: d.id, ...d.data() }));
    docs.sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    const g = $("myphotos");
    g.innerHTML = docs.map(d => {
      const thumb = (d.url || "").replace("/upload/", "/upload/w_160,h_160,c_fill,q_auto,f_auto/");
      return `<div class="mytile"><img src="${thumb}" alt="" loading="lazy">
        <button class="del" data-id="${d.id}" aria-label="Supprimer">✕</button>
        ${d.gps ? "" : '<span class="nogps">sans GPS</span>'}</div>`;
    }).join("");
    g.querySelectorAll(".del").forEach(b => b.onclick = () => delPhoto(b.dataset.id));
  }, e => { $("up-status").innerHTML = `<span class="err">${e.code || e}</span>`; });
}
async function delPhoto(id) {
  // retire la fiche Firestore -> disparaît de la carte et de la grille.
  // (le fichier reste sur Cloudinary : le supprimer exigerait la clé secrète,
  //  qu'on n'embarque pas ; sans conséquence, on est loin des quotas gratuits.)
  try {
    const { db, doc, deleteDoc } = await fb();
    await deleteDoc(doc(db, "photos", id));
  } catch (e) { $("up-status").innerHTML = `<span class="err">suppr.: ${e.code || e}</span>`; }
}

// ---- go -------------------------------------------------------------------
// on relance sur le même perso (cookie), tout en gardant le bouton ⇄ pour
// changer ; ré-écriture = on repousse l'expiration du cookie à chaque ouverture
if (me && CREW[me]) { saveMe(me); start(); } else renderPick();
