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
// Plafond côté client (Cloudinary gratuit = 100 Mo/fichier en upload non signé).
const MAX_VIDEO_BYTES = 100 * 1024 * 1024;
const isVideoBlob = b => (b && b.type || "").startsWith("video/");
// Vignette : photo -> crop carré ; vidéo -> poster (1re frame) en .jpg.
function mediaThumb(url, video, px) {
  if (!url) return "";
  return video
    ? url.replace("/video/upload/", `/video/upload/w_${px},h_${px},c_fill,so_0/`)
         .replace(/\.[a-z0-9]+($|\?)/i, ".jpg$1")
    : url.replace("/upload/", `/upload/w_${px},h_${px},c_fill,q_auto,f_auto/`);
}
function validCoords(lat, lng) {
  return Number.isFinite(lat) && Number.isFinite(lng)
    && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
}
const hasLocation = d => !!d && validCoords(d.lat, d.lng);

// ---- choix manuel de la localisation (média sans GPS) ---------------------
// Leaflet chargé À LA DEMANDE (rien de plus au démarrage quand le GPS est là).
let leafletP = null;
function loadLeaflet() {
  if (window.L) return Promise.resolve();
  if (leafletP) return leafletP;
  leafletP = new Promise((resolve, reject) => {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
    document.head.appendChild(css);
    const js = document.createElement("script");
    js.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
    const failed = () => {
      leafletP = null;   // une panne CDN ponctuelle doit pouvoir être retentée
      css.remove();
      js.remove();
      reject(new Error("leaflet"));
    };
    js.onload = () => window.L ? resolve() : failed();
    js.onerror = failed;
    document.head.appendChild(js);
  });
  return leafletP;
}

let locMap = null;
let lastUploadLocation = null;
// Ouvre la carte, l'utilisateur cadre sous l'épingle centrale (ou "Ma position").
// En édition, part du lieu existant et propose Annuler au lieu d'Ignorer.
// Résout {lat,lng} si Valider, null si Ignorer/Annuler ; lève si la carte échoue.
async function askLocation({ initial = null, editing = false } = {}) {
  try { await loadLeaflet(); }
  catch (_) {
    leafletP = null;
    throw new Error("Impossible d'ouvrir la carte. Vérifie la connexion.");
  }

  const modal = $("loc-modal");
  const previousFocus = document.activeElement;
  const hasInitial = hasLocation(initial);
  const remembered = !editing && hasLocation(lastUploadLocation)
    ? lastUploadLocation : null;

  $("loc-head").textContent = editing
    ? hasInitial ? "Modifier le lieu" : "Ajouter un lieu"
    : "Où était-ce ?";
  $("loc-hint").textContent = editing
    ? "Déplace la carte sous l'épingle, ou utilise ta position actuelle."
    : "Pas de localisation dans ce média. Déplace la carte sous l'épingle, ou utilise ta position.";
  $("loc-skip").textContent = editing ? "Annuler" : "Ignorer";
  $("loc-here").disabled = false;
  $("loc-here").textContent = "◉ Ma position";

  modal.classList.remove("hidden");
  try {
    if (!locMap) {
      locMap = L.map("loc-map", { zoomControl: true, attributionControl: true, minZoom: 2 })
        .setView([16.5, -14], 4);   // Sahel/Sénégal par défaut
      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        { subdomains: "abcd", maxZoom: 19, attribution: "&copy; OpenStreetMap &copy; CARTO" }).addTo(locMap);
    }
    if (hasInitial) locMap.setView([initial.lat, initial.lng], 14);
    else if (remembered) locMap.setView([remembered.lat, remembered.lng], 14);
    else locMap.setView([16.5, -14], 4);
  } catch (_) {
    try { if (locMap) locMap.remove(); } catch (_) {}
    locMap = null;
    modal.classList.add("hidden");
    throw new Error("Impossible d'ouvrir la carte. Réessaie.");
  }

  return new Promise(resolve => {
    const ok = $("loc-ok"), skip = $("loc-skip"), here = $("loc-here");
    const backgrounds = ["login", "pick", "dash", "media-modal"]
      .map($)
      .filter(el => el && !el.classList.contains("hidden"));
    const backgroundState = backgrounds.map(el => ({
      el,
      inert: el.hasAttribute("inert"),
      ariaHidden: el.getAttribute("aria-hidden"),
    }));
    let settled = false;
    let sizeTimer = null;
    const onKeydown = e => {
      if (e.key === "Escape") {
        e.preventDefault();
        done(null);
        return;
      }
      if (e.key !== "Tab") return;
      const items = [here, skip, ok].filter(el => !el.disabled);
      const first = items[0], last = items[items.length - 1];
      if (!modal.contains(document.activeElement)) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      } else if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    };
    const done = val => {
      if (settled) return;
      settled = true;
      clearTimeout(sizeTimer);
      ok.onclick = skip.onclick = here.onclick = null;
      modal.removeEventListener("keydown", onKeydown);
      modal.classList.add("hidden");
      for (const state of backgroundState) {
        if (!state.inert) state.el.removeAttribute("inert");
        if (state.ariaHidden == null) state.el.removeAttribute("aria-hidden");
        else state.el.setAttribute("aria-hidden", state.ariaHidden);
      }
      if (previousFocus && previousFocus.focus) previousFocus.focus();
      resolve(val);
    };
    ok.onclick = () => {
      const c = locMap.getCenter().wrap();
      const picked = { lat: +c.lat.toFixed(6), lng: +c.lng.toFixed(6) };
      if (!editing) lastUploadLocation = picked;
      done(picked);
    };
    skip.onclick = () => done(null);
    here.onclick = () => {
      if (!navigator.geolocation) {
        $("loc-hint").textContent = "Position actuelle indisponible. Déplace la carte sous l'épingle.";
        return;
      }
      here.disabled = true; here.textContent = "…";
      navigator.geolocation.getCurrentPosition(
        p => {
          if (settled) return;
          locMap.setView([p.coords.latitude, p.coords.longitude], 14);
          here.disabled = false; here.textContent = "◉ Ma position";
        },
        _ => {
          if (settled) return;
          here.disabled = false; here.textContent = "◉ Ma position";
          $("loc-hint").textContent = "Position actuelle refusée ou indisponible. Déplace la carte sous l'épingle.";
        },
        { enableHighAccuracy: true, timeout: 8000 });
    };
    modal.addEventListener("keydown", onKeydown);
    ok.focus({ preventScroll: true });
    for (const state of backgroundState) {
      state.el.setAttribute("aria-hidden", "true");
      state.el.setAttribute("inert", "");
    }
    sizeTimer = setTimeout(() => {
      if (!settled) locMap.invalidateSize();
    }, 60);   // la carte a une taille une fois le modal visible
  });
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
          addDoc: fs.addDoc, deleteDoc: fs.deleteDoc, updateDoc: fs.updateDoc,
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
        for (const it of (items || [])) {
          const lat = it.lat ?? null, lng = it.lng ?? null, date = it.date || null;
          if (it.video && it.path) {
            // vidéo : le natif a copié le fichier en cache (pas de base64) ->
            // on le relit via la WebView (convertFileSrc) puis on l'uploade.
            const src = (CAP && CAP.convertFileSrc) ? CAP.convertFileSrc(it.path) : it.path;
            const blob = await (await fetch(src)).blob();
            await uploadPhoto(blob, lat, lng, date, true);
          } else {
            await uploadPhoto(b64toBlob(it.base64), lat, lng, date, false);
          }
        }
      } catch (e) { $("up-status").innerHTML = `<span class="err">erreur: ${e.message || e}</span>`; }
    } else {
      $("fallback-input").click();
    }
  };
  $("fallback-input").onchange = async e => {
    for (const f of e.target.files) {
      let lat = null, lng = null, date = null;
      const video = (f.type || "").startsWith("video/");
      if (video) {
        // Les vidéos n'ont pas d'EXIF ; leur GPS (atome QuickTime) n'est pas
        // lisible en navigateur -> sans position, placée par date (lastModified).
        if (f.lastModified) date = new Date(f.lastModified).toISOString().slice(0, 10);
      } else {
        const exifr = await import("https://cdn.jsdelivr.net/npm/exifr@7.1.3/dist/full.esm.mjs");
        try {
          const g = await exifr.gps(f);
          if (g) { lat = g.latitude; lng = g.longitude; }
          const d = await exifr.parse(f, ["DateTimeOriginal"]);
          if (d && d.DateTimeOriginal) date = d.DateTimeOriginal.toISOString().slice(0, 10);
        } catch (_) {}
      }
      await uploadPhoto(f, lat, lng, date, video);
    }
    e.target.value = "";
  };
}

async function uploadPhoto(blob, lat, lng, date, video = isVideoBlob(blob)) {
  const st = $("up-status");
  const noun = video ? "vidéo" : "photo";
  if (video && blob.size > MAX_VIDEO_BYTES) {
    st.innerHTML = `<span class="err">vidéo trop lourde (${Math.round(blob.size / 1048576)} Mo, max 100) — filme plus court</span>`;
    return;
  }
  // pas de localisation détectée -> l'utilisateur la choisit sur une mini-carte
  let manual = false;
  let locationError = false;
  if (!validCoords(lat, lng)) {
    lat = lng = null;   // une paire partielle/invalide ne doit jamais être gardée
    let picked;
    try { picked = await askLocation(); }
    catch (e) {
      // L'upload reste possible : le nouveau bouton du détail permettra
      // d'ajouter le lieu plus tard, une fois la carte de nouveau accessible.
      locationError = true;
    }
    if (picked) { lat = picked.lat; lng = picked.lng; manual = true; }
  }
  const located = validCoords(lat, lng);
  st.textContent = "envoi…";
  try {
    // le FICHIER va sur Cloudinary (gratuit, sans carte) ; seules les
    // MÉTADONNÉES (nom, position, date, url, type) vont dans Firestore.
    // Endpoint distinct pour la vidéo (/video/upload) vs l'image (/image/upload).
    const form = new FormData();
    form.append("file", blob);
    form.append("upload_preset", CLOUDINARY.preset);
    const res = await fetch(
      `https://api.cloudinary.com/v1_1/${CLOUDINARY.cloudName}/${video ? "video" : "image"}/upload`,
      { method: "POST", body: form });
    if (!res.ok) throw new Error("upload " + res.status);
    const link = (await res.json()).secure_url;

    const { db, addDoc, collection, ts } = await fb();
    await addDoc(collection(db, "photos"), {
      name: me, car: CREW[me], url: link, type: video ? "video" : "image",
      lat: located ? lat : null, lng: located ? lng : null,
      gps: located && !manual, manual: located && manual,
      date: date || new Date().toISOString().slice(0, 10), at: ts(),
    });
    // la grille "mes photos" se met à jour toute seule (onSnapshot)
    st.innerHTML = manual
      ? `<span class="ok">${noun} ajoutée à l'endroit choisi ✓</span>`
      : located
        ? `<span class="ok">${noun} ajoutée avec sa position ✓</span>`
        : locationError
          ? `<span class="ok">${noun} ajoutée</span> (carte indisponible → ajoute le lieu plus tard)`
          : `<span class="ok">${noun} ajoutée</span> (sans lieu → n'apparaîtra pas sur la carte)`;
  } catch (e) { st.innerHTML = `<span class="err">erreur: ${e.code || e}</span>`; }
}

// ---- mes photos : grille live + suppression -------------------------------
// --- galerie perso : groupée par JOUR (récent d'abord) + filtre photos/vidéos.
// Purement client (aucun changement de schéma) -> fiable même avec beaucoup de
// médias. Les données arrivent en live (onSnapshot) et on re-rend à chaque
// snapshot ou changement de filtre. ---
let myDocs = [];
let mediaFilter = "all";   // "all" | "image" | "video"
const isVid = d => d.type === "video" || /\/video\/upload\//.test(d.url || "");
const atMs = d => { try { return d.at ? d.at.toMillis() : 0; } catch (_) { return 0; } };

function dayLabel(dateStr) {
  if (!dateStr) return "Sans date";
  const today = new Date().toISOString().slice(0, 10);
  const yest = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  if (dateStr === today) return "Aujourd'hui";
  if (dateStr === yest) return "Hier";
  return new Date(dateStr + "T12:00:00")
    .toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "long" });
}

function renderMyPhotos() {
  const g = $("myphotos");
  const docs = myDocs.filter(d =>
    mediaFilter === "all" ? true : mediaFilter === "video" ? isVid(d) : !isVid(d));

  const count = $("media-count");
  if (count) count.textContent = myDocs.length ? `· ${myDocs.length}` : "";

  if (!docs.length) {
    g.innerHTML = `<p class="hint empty">${myDocs.length
      ? "Aucun média de ce type." : "Pas encore de média — ajoute-en un ci-dessus."}</p>`;
    return;
  }

  // regroupe par jour en conservant l'ordre (déjà trié récent -> ancien)
  const groups = [], byDay = new Map();
  for (const d of docs) {
    const day = d.date || "";
    let grp = byDay.get(day);
    if (!grp) { grp = { day, items: [] }; byDay.set(day, grp); groups.push(grp); }
    grp.items.push(d);
  }

  const tile = d => {
    const video = isVid(d);
    const thumb = mediaThumb(d.url, video, 160);
    return `<div class="mytile${video ? " is-video" : ""}" data-id="${d.id}" role="button" tabindex="0">
      <img src="${thumb}" alt="" loading="lazy">
      ${video ? '<span class="playbadge">▶</span>' : ""}
      ${d.caption ? '<span class="capbadge" aria-label="Avec légende">💬</span>' : ""}
      <button class="del" data-id="${d.id}" aria-label="Supprimer">✕</button>
      ${hasLocation(d) ? "" : '<span class="nogps">sans lieu</span>'}</div>`;
  };

  g.innerHTML = groups.map(grp =>
    `<div class="dayhead"><span>${dayLabel(grp.day)}</span><em>${grp.items.length}</em></div>
     <div class="mygrid">${grp.items.map(tile).join("")}</div>`).join("");
  g.querySelectorAll(".del").forEach(b => b.onclick = e => { e.stopPropagation(); delPhoto(b.dataset.id); });
  g.querySelectorAll(".mytile").forEach(t => {
    t.onclick = () => openMedia(t.dataset.id, t);
    t.onkeydown = e => {
      if (e.target !== t || (e.key !== "Enter" && e.key !== " ")) return;
      e.preventDefault();
      openMedia(t.dataset.id, t);
    };
  });
}

// --- détail d'un média : voir en grand + éditer légende et lieu ------------
let editingId = null;
let mediaSession = 0;
let mediaReturnFocus = null;
let mediaReturnId = null;
let locationWriteSeq = 0;
let captionWriteSeq = 0;
function setMediaLocationStatus(message = "", error = false) {
  const status = $("media-location-status");
  status.textContent = message;
  status.classList.toggle("err", error);
  status.classList.toggle("ok", !!message && !error);
}
function renderMediaLocation(d) {
  const located = hasLocation(d);
  const box = $("media-location");
  box.classList.toggle("missing", !located);
  $("media-location-label").textContent = located
    ? d.manual ? "Lieu choisi" : d.gps ? "GPS du média" : "Lieu enregistré"
    : "Sans lieu";
  $("media-location-detail").textContent = located
    ? "Visible sur la carte"
    : "N'apparaît pas sur la carte";
  $("media-location-edit").textContent = located ? "Modifier" : "Ajouter un lieu";
}
function trapMediaFocus(e) {
  const modal = $("media-modal");
  if (e.key === "Escape") {
    e.preventDefault();
    closeMedia();
    return;
  }
  if (e.key !== "Tab") return;
  const items = [...modal.querySelectorAll("button, input, video[controls]")]
    .filter(el => !el.disabled && el.tabIndex !== -1);
  const first = items[0], last = items[items.length - 1];
  if (!first) return;
  if (!modal.contains(document.activeElement)) {
    e.preventDefault();
    (e.shiftKey ? last : first).focus();
  } else if (e.shiftKey && document.activeElement === first) {
    e.preventDefault(); last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault(); first.focus();
  }
}
function closeMedia() {
  const returnId = editingId || mediaReturnId;
  const fallbackFocus = mediaReturnFocus;
  mediaSession++;
  locationWriteSeq++;
  captionWriteSeq++;
  const v = $("media-view").querySelector("video");
  if (v) { try { v.pause(); } catch (_) {} }
  $("media-view").innerHTML = "";
  $("media-modal").classList.add("hidden");
  $("dash").removeAttribute("inert");
  $("dash").removeAttribute("aria-hidden");
  editingId = null;
  mediaReturnFocus = null;
  mediaReturnId = null;
  const freshTile = [...document.querySelectorAll(".mytile")]
    .find(t => t.dataset.id === returnId);
  const target = freshTile || (fallbackFocus && fallbackFocus.isConnected ? fallbackFocus : null);
  if (target && target.focus) target.focus();
}
function openMedia(id, trigger = null) {
  const d = myDocs.find(x => x.id === id);
  if (!d) return;
  mediaSession++;
  locationWriteSeq++;
  captionWriteSeq++;
  editingId = id;
  mediaReturnId = id;
  mediaReturnFocus = trigger || document.activeElement;
  const video = isVid(d);
  $("media-view").innerHTML = video
    ? `<video src="${d.url}" controls playsinline poster="${mediaThumb(d.url, true, 600)}"></video>`
    : `<img src="${mediaThumb(d.url, false, 800)}" alt="">`;
  $("media-caption").value = d.caption || "";
  $("media-save").disabled = false;
  $("media-save").textContent = "Enregistrer";
  $("media-location-edit").disabled = false;
  renderMediaLocation(d);
  setMediaLocationStatus();
  $("media-modal").classList.remove("hidden");
  $("media-close").focus({ preventScroll: true });
  $("dash").setAttribute("aria-hidden", "true");
  $("dash").setAttribute("inert", "");
}
function initMediaModal() {
  $("media-close").onclick = closeMedia;
  $("media-modal").onclick = e => { if (e.target === $("media-modal")) closeMedia(); };
  $("media-modal").onkeydown = trapMediaFocus;
  $("media-location-edit").onclick = async () => {
    const id = editingId;
    const d = myDocs.find(x => x.id === id);
    if (!id || !d) return;
    const session = mediaSession;
    const btn = $("media-location-edit");
    let writeSeq = null;
    setMediaLocationStatus();
    try {
      const picked = await askLocation({
        initial: hasLocation(d) ? { lat: d.lat, lng: d.lng } : null,
        editing: true,
      });
      if (!picked) return;
      const patch = {
        lat: picked.lat, lng: picked.lng,
        gps: false, manual: true,
      };
      writeSeq = ++locationWriteSeq;
      btn.disabled = true;
      btn.textContent = "…";
      const { db, doc, updateDoc } = await fb();
      await updateDoc(doc(db, "photos", id), patch);
      const current = myDocs.find(x => x.id === id);
      if (current) Object.assign(current, patch);
      renderMyPhotos();
      if (mediaSession === session && editingId === id) {
        renderMediaLocation(current || { ...d, ...patch });
        setMediaLocationStatus("Lieu enregistré ✓");
      }
    } catch (e) {
      if (mediaSession === session && editingId === id) {
        setMediaLocationStatus(`Lieu non enregistré : ${e.code || e.message || e}`, true);
      }
    } finally {
      if (writeSeq != null && writeSeq === locationWriteSeq) {
        btn.disabled = false;
        if (mediaSession === session && editingId === id) {
          const current = myDocs.find(x => x.id === id);
          if (current) renderMediaLocation(current);
        }
      }
    }
  };
  $("media-save").onclick = async () => {
    const id = editingId;
    const d = myDocs.find(x => x.id === id);
    if (!id || !d) return;
    const session = mediaSession;
    const caption = $("media-caption").value.trim();
    if (caption === (d.caption || "")) {
      closeMedia();
      return;
    }
    const writeSeq = ++captionWriteSeq;
    const btn = $("media-save"); btn.disabled = true; btn.textContent = "…";
    try {
      const { db, doc, updateDoc } = await fb();
      await updateDoc(doc(db, "photos", id), { caption });
      const current = myDocs.find(x => x.id === id);
      if (current) current.caption = caption;
      renderMyPhotos();
      if (mediaSession === session && editingId === id) closeMedia();
    } catch (e) {
      if (mediaSession === session && editingId === id) {
        setMediaLocationStatus(`Légende non enregistrée : ${e.code || e}`, true);
      }
    } finally {
      if (writeSeq === captionWriteSeq) {
        btn.disabled = false;
        btn.textContent = "Enregistrer";
      }
    }
  };
  $("media-del").onclick = () => { const id = editingId; closeMedia(); if (id) delPhoto(id); };
}

async function watchMyPhotos() {
  const { db, collection, query, where, onSnapshot } = await fb();
  initMediaModal();
  document.querySelectorAll("#mediafilter button").forEach(b => {
    b.onclick = () => {
      mediaFilter = b.dataset.f;
      document.querySelectorAll("#mediafilter button").forEach(x => x.classList.toggle("on", x === b));
      renderMyPhotos();
    };
  });
  onSnapshot(query(collection(db, "photos"), where("name", "==", me)), snap => {
    myDocs = [];
    snap.forEach(d => myDocs.push({ id: d.id, ...d.data() }));
    // récent d'abord : par date puis par horodatage d'envoi
    myDocs.sort((a, b) => (b.date || "").localeCompare(a.date || "") || atMs(b) - atMs(a));
    renderMyPhotos();
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
