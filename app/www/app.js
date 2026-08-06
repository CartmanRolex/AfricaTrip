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
const TRIP_ID = "africa-trip-01";
const TRACK_SCHEMA_VERSION = 2;
// Deux heures × un point/minute = 120 points maximum, sous le cap Firestore
// de 160 tout en évitant de multiplier les documents à relire sur le site.
const TRACK_BUCKET_MS = 2 * 60 * 60 * 1000;
const DEVICE_KEY = `${TRIP_ID}:device-id`;
const DEVICE_COOKIE = "crew-device-v2";
const ASSIGNMENT_KEY = `${TRIP_ID}:assignment:`;
const ASSIGNMENT_COOKIE = "crew-mode-v2-";
const OUTBOX_DB = `${TRIP_ID}-outbox-v2`;
const OUTBOX_STORE = "events";

const ASSIGNMENT_CHOICES = {
  hugodouard: { mode: "vehicle", vehicleId: "hugodouard", label: "Hugodouard", car: 1 },
  "paul-pot": { mode: "vehicle", vehicleId: "paul-pot", label: "Paul Pot", car: 2 },
  independent: { mode: "independent", vehicleId: null, label: "À pied / autre", car: "obs" },
  paused: { mode: "paused", vehicleId: null, label: "Pause", car: "obs" },
};

function personIdFor(name) {
  return (name || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
function randomToken() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (window.crypto && typeof window.crypto.getRandomValues === "function") {
    window.crypto.getRandomValues(bytes);
    return [...bytes].map(x => x.toString(16).padStart(2, "0")).join("");
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
function storedValue(key) {
  try { return localStorage.getItem(key); } catch (_) { return null; }
}
function storeValue(key, value) {
  try { localStorage.setItem(key, value); return true; } catch (_) { return false; }
}
function readCookieValue(name) {
  const prefix = `${name}=`;
  const part = document.cookie.split(";").map(x => x.trim()).find(x => x.startsWith(prefix));
  if (!part) return null;
  try { return decodeURIComponent(part.slice(prefix.length)); } catch (_) { return part.slice(prefix.length); }
}
function writeCookieValue(name, value) {
  document.cookie = `${name}=${encodeURIComponent(value)}; Max-Age=${60 * 60 * 24 * 400}; Path=/; SameSite=Lax`;
}
function loadDeviceId() {
  const saved = readCookieValue(DEVICE_COOKIE) || storedValue(DEVICE_KEY);
  if (saved && /^[a-z0-9-]{8,80}$/i.test(saved)) {
    storeValue(DEVICE_KEY, saved);
    writeCookieValue(DEVICE_COOKIE, saved);
    return saved;
  }
  const id = `dev-${randomToken()}`;
  storeValue(DEVICE_KEY, id);
  writeCookieValue(DEVICE_COOKIE, id);
  return id;
}
const DEVICE_ID = loadDeviceId();

function choiceKey(mode, vehicleId) {
  if (mode === "vehicle" && ASSIGNMENT_CHOICES[vehicleId]) return vehicleId;
  if (mode === "independent") return "independent";
  if (mode === "paused") return "paused";
  return "paused";
}
// Affectation par defaut d'une personne : SA voiture d'apres le roster. Le
// defaut precedent etait Pause, si bien qu'un equipier qui n'avait rien choisi
// enregistrait ses points (et ses photos) en « obs » — hors voiture — et son
// trajet ne rejoignait jamais celui de sa voiture sur le site.
// Consequence assumee : le partage GPS demarre des l'ouverture de l'app pour
// quelqu'un du roster. « Pause » reste a un tap pour l'arreter.
function defaultAssignmentFor(personId) {
  const entry = Object.entries(CREW).find(([name]) => personIdFor(name) === personId);
  const car = entry && entry[1];
  if (car === 1) return ASSIGNMENT_CHOICES.hugodouard;
  if (car === 2) return ASSIGNMENT_CHOICES["paul-pot"];
  return ASSIGNMENT_CHOICES.paused;   // observateur ou prenom inconnu
}
function loadAssignmentChoice(personId) {
  try {
    const cookieKey = readCookieValue(ASSIGNMENT_COOKIE + personId);
    if (cookieKey && ASSIGNMENT_CHOICES[cookieKey]) return ASSIGNMENT_CHOICES[cookieKey];
    const saved = JSON.parse(storedValue(ASSIGNMENT_KEY + personId) || "null");
    if (!saved) return defaultAssignmentFor(personId);
    const key = choiceKey(saved && saved.mode, saved && saved.vehicleId);
    return ASSIGNMENT_CHOICES[key];
  } catch (_) { return defaultAssignmentFor(personId); }
}
function saveAssignmentChoice(personId, assignment) {
  storeValue(ASSIGNMENT_KEY + personId, JSON.stringify({
    mode: assignment.mode, vehicleId: assignment.vehicleId,
  }));
  writeCookieValue(ASSIGNMENT_COOKIE + personId,
    choiceKey(assignment.mode, assignment.vehicleId));
}
function makeAssignment(person, sessionId, choice, reason) {
  const personId = personIdFor(person), effectiveAtMs = Date.now();
  return {
    schemaVersion: TRACK_SCHEMA_VERSION,
    tripId: TRIP_ID,
    assignmentId: `asn-${personId}-${effectiveAtMs}-${randomToken()}`,
    personId,
    displayName: person,
    vehicleId: choice.vehicleId,
    mode: choice.mode,
    effectiveAtMs,
    sessionId,
    deviceId: DEVICE_ID,
    reason,
  };
}
function legacyCar(assignment) {
  return assignment.vehicleId === "hugodouard" ? 1
    : assignment.vehicleId === "paul-pot" ? 2 : "obs";
}

// ---- file d'envoi locale -------------------------------------------------
// IndexedDB garde les points hors ligne sans la petite limite de localStorage.
// Chaque entrée a un identifiant déterministe et ne quitte la file qu'après une
// transaction Firestore réussie. localStorage reste un secours pour les rares
// WebViews où IndexedDB ne peut pas être ouvert.
let outboxDbP = null;
let outboxSeq = 0;
let outboxFlushing = false;
let outboxFlushRequested = false;
let outboxRetryTimer = null;
let outboxRetryMs = 2000;
const OUTBOX_FALLBACK_KEY = `${TRIP_ID}:outbox-fallback-v2`;

function openOutbox() {
  if (outboxDbP) return outboxDbP;
  if (!window.indexedDB) return Promise.reject(new Error("IndexedDB indisponible"));
  outboxDbP = new Promise((resolve, reject) => {
    const request = window.indexedDB.open(OUTBOX_DB, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(OUTBOX_STORE)) {
        const store = db.createObjectStore(OUTBOX_STORE, { keyPath: "id" });
        store.createIndex("orderKey", "orderKey", { unique: false });
      }
    };
    request.onsuccess = () => {
      const db = request.result;
      db.onversionchange = () => { db.close(); outboxDbP = null; };
      resolve(db);
    };
    request.onerror = () => { outboxDbP = null; reject(request.error || new Error("IndexedDB")); };
    request.onblocked = () => { outboxDbP = null; reject(new Error("IndexedDB bloquée")); };
  });
  return outboxDbP;
}
function txDone(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error || new Error("IndexedDB"));
    tx.onabort = () => reject(tx.error || new Error("IndexedDB interrompue"));
  });
}
function fallbackEntries() {
  try {
    const parsed = JSON.parse(storedValue(OUTBOX_FALLBACK_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter(x => x && x.id && x.orderKey) : [];
  } catch (_) { return []; }
}
function saveFallback(entries) {
  if (!storeValue(OUTBOX_FALLBACK_KEY, JSON.stringify(entries))) {
    throw new Error("Stockage local plein");
  }
}
async function outboxPut(item) {
  try {
    const db = await openOutbox();
    const tx = db.transaction(OUTBOX_STORE, "readwrite");
    tx.objectStore(OUTBOX_STORE).put(item);
    await txDone(tx);
  } catch (_) {
    const entries = fallbackEntries();
    const i = entries.findIndex(x => x.id === item.id);
    if (i >= 0) entries[i] = item; else entries.push(item);
    entries.sort((a, b) => a.orderKey.localeCompare(b.orderKey));
    saveFallback(entries);
  }
}
async function firstIndexedEntry() {
  try {
    const db = await openOutbox();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(OUTBOX_STORE, "readonly");
      const request = tx.objectStore(OUTBOX_STORE).index("orderKey").openCursor();
      request.onsuccess = () => resolve(request.result ? request.result.value : null);
      request.onerror = () => reject(request.error || new Error("IndexedDB"));
    });
  } catch (_) { return null; }
}
async function outboxFirst() {
  const indexed = await firstIndexedEntry();
  const fallback = fallbackEntries()[0] || null;
  if (!indexed) return fallback ? { backend: "fallback", item: fallback } : null;
  if (!fallback || indexed.orderKey <= fallback.orderKey) return { backend: "indexed", item: indexed };
  return { backend: "fallback", item: fallback };
}
async function outboxDelete(ref) {
  if (ref.backend === "fallback") {
    saveFallback(fallbackEntries().filter(x => x.id !== ref.item.id));
    return;
  }
  const db = await openOutbox();
  const tx = db.transaction(OUTBOX_STORE, "readwrite");
  tx.objectStore(OUTBOX_STORE).delete(ref.item.id);
  await txDone(tx);
}
function queuedItem(item) {
  const now = Date.now();
  return {
    ...item,
    queuedAtMs: now,
    orderKey: `${String(now).padStart(13, "0")}-${String(++outboxSeq).padStart(6, "0")}-${item.id}`,
  };
}
async function enqueueOutbox(item) {
  await outboxPut(queuedItem(item));
  scheduleOutboxFlush(0);
}
function scheduleOutboxFlush(delay = 0) {
  outboxFlushRequested = true;
  clearTimeout(outboxRetryTimer);
  outboxRetryTimer = setTimeout(flushOutbox, delay);
}

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
let _fbP = null;
async function fb() {
  if (_fb) return _fb;
  if (_fbP) return _fbP;
  _fbP = (async () => {
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
            onSnapshot: fs.onSnapshot, runTransaction: fs.runTransaction,
            ts: fs.serverTimestamp };
    return _fb;
  })();
  try { return await _fbP; }
  catch (e) { _fbP = null; throw e; }
}

function firestoreAssignment(item) {
  const a = item.assignment;
  return { ...a, effectiveAt: new Date(a.effectiveAtMs) };
}
function firestorePoint(point) {
  return { ...point, capturedAt: new Date(point.capturedAtMs) };
}
async function deliverOutbox(item) {
  const { db, doc, setDoc, runTransaction } = await fb();
  if (item.kind === "assignment") {
    const a = item.assignment;
    await setDoc(doc(db, "trips", TRIP_ID, "assignmentEvents", a.assignmentId),
      firestoreAssignment(item));
    return;
  }
  if (item.kind !== "point") throw new Error("Événement local inconnu");

  const point = item.point;
  const pointData = firestorePoint(point);
  const bucketStartMs = Math.floor(point.capturedAtMs / TRACK_BUCKET_MS) * TRACK_BUCKET_MS;
  // Une affectation par chunk évite de mélanger deux voitures et garantit
  // une marge sous le cap de 160, même après plusieurs changements.
  const chunkId = `${point.personId}_${point.sessionId}_${point.assignmentId}_${bucketStartMs}`;
  const chunkRef = doc(db, "trips", TRIP_ID, "trackChunks", chunkId);
  const latestRef = doc(db, "trips", TRIP_ID, "latest", point.personId);

  await runTransaction(db, async transaction => {
    const latestSnap = await transaction.get(latestRef);
    const old = latestSnap.exists() ? latestSnap.data() : null;
    const isExactRetry = !!old && point.capturedAtMs === old.capturedAtMs
      && point.pointId === old.pointId;
    const isNewer = !old || !Number.isFinite(old.capturedAtMs)
      || point.capturedAtMs > old.capturedAtMs || isExactRetry;

    transaction.set(chunkRef, {
      schemaVersion: TRACK_SCHEMA_VERSION,
      tripId: TRIP_ID,
      personId: point.personId,
      displayName: point.displayName,
      sessionId: point.sessionId,
      deviceId: point.deviceId,
      assignmentId: point.assignmentId,
      vehicleId: point.vehicleId,
      mode: point.mode,
      bucketStartAt: new Date(bucketStartMs),
      bucketStartMs,
      lastPointId: point.pointId,
      points: { [point.pointId]: pointData },
    }, { merge: true });

    if (isNewer) {
      transaction.set(latestRef, { schemaVersion: TRACK_SCHEMA_VERSION, ...pointData });
    }
  });
}

async function flushOutbox() {
  if (outboxFlushing) {
    outboxFlushRequested = true;
    return;
  }
  outboxFlushing = true;
  outboxFlushRequested = false;
  clearTimeout(outboxRetryTimer);
  let failed = false;
  try {
    let ref;
    while ((ref = await outboxFirst())) {
      await deliverOutbox(ref.item);
      await outboxDelete(ref);
      outboxRetryMs = 2000;
      if (ref.item.kind === "point" && activeDashboard
          && activeDashboard.active && activeDashboard.position) {
        activeDashboard.position.markSent(ref.item.point);
      }
    }
  } catch (e) {
    failed = true;
    if (activeDashboard && activeDashboard.active && activeDashboard.position) {
      activeDashboard.position.markQueued(e);
    }
  } finally {
    const pending = !failed && !!(await outboxFirst());
    const requested = outboxFlushRequested;
    outboxFlushing = false;
    if (failed) {
      scheduleOutboxFlush(outboxRetryMs);
      outboxRetryMs = Math.min(outboxRetryMs * 2, 60000);
    } else if (requested || pending) {
      scheduleOutboxFlush(0);
    }
  }
}
window.addEventListener("online", () => scheduleOutboxFlush(0));

// ---- porte d'entrée : mot de passe partagé (une seule fois) ----------------
// L'équipage partage UN mot de passe (compte Firebase unique). Firebase garde
// la session, donc on ne le retape qu'au 1er lancement (ou nouveau tel). Le
// site, lui, lit tout en public : aucune de ces vérifs ne le concerne.
let pendingAuthGate = null;
function cancelPendingAuth() {
  const gate = pendingAuthGate;
  pendingAuthGate = null;
  if (!gate) return;
  gate.finished = true;
  if (gate.unsubscribe) gate.unsubscribe();
  gate.resolve(false);
}
async function requireAuth(generation) {
  cancelPendingAuth();
  const { onAuth } = await fb();
  if (generation !== startGeneration) return false;
  return new Promise(resolve => {
    let shown = false;
    const gate = { unsubscribe: null, resolve, finished: false };
    const finish = value => {
      if (gate.finished) return;
      gate.finished = true;
      if (pendingAuthGate === gate) pendingAuthGate = null;
      if (gate.unsubscribe) gate.unsubscribe();
      resolve(value);
    };
    pendingAuthGate = gate;
    gate.unsubscribe = onAuth(user => {
      if (generation !== startGeneration) return finish(false);
      // on n'accepte QUE le compte équipage : une session laissée par une
      // ancienne version (anonyme, email nul) ne doit PAS ouvrir sans mot de
      // passe -> sinon on tombe sur le dashboard sans jamais le demander
      if (user && user.email === AUTH_EMAIL) {
        finish(true);
      } else if (!shown) { shown = true; showLogin(generation); }
    });
    // Garde-fou si un mock appelle le callback de façon synchrone.
    if (gate.finished && gate.unsubscribe) gate.unsubscribe();
  });
}
function showLogin(generation) {
  $("pick").classList.add("hidden");
  $("dash").classList.add("hidden");
  $("login").classList.remove("hidden");
  const input = $("pw-input"), err = $("pw-err"), go = $("pw-go");
  go.disabled = false;
  err.textContent = "un seul mot de passe pour toute l'équipe";
  input.focus();
  const submit = async () => {
    if (generation !== startGeneration) return;
    if (!input.value.trim()) return;
    go.disabled = true; err.textContent = "connexion…";
    try {
      const authGateAtSubmit = pendingAuthGate;
      const { signIn } = await fb();
      await signIn(input.value.trim());
      // succès -> onAuth(user) déclenche resolve() de requireAuth -> start()
      // Si l'import Firebase avait échoué avant la création de cette gate,
      // relancer explicitement le démarrage après une connexion réussie.
      if (!authGateAtSubmit && !pendingAuthGate && generation === startGeneration) start();
    } catch (e) {
      if (generation !== startGeneration) return;
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
let activeDashboard = null;
let startGeneration = 0;

function cleanupDashboard() {
  const lifecycle = activeDashboard;
  activeDashboard = null;
  if (!lifecycle) return;
  lifecycle.active = false;
  clearTimeout(lifecycle.statsTimer);
  clearInterval(lifecycle.ageTimer);
  if (lifecycle.photoUnsub) {
    try { lifecycle.photoUnsub(); } catch (_) {}
    lifecycle.photoUnsub = null;
  }
  if (lifecycle.position) lifecycle.position.stop();
  if (editingId) closeMedia();
  myDocs = [];
  renderMyPhotos();
}

function assignmentLabel(assignment) {
  if (assignment.mode === "paused") return "⏸️ Pause";
  if (assignment.vehicleId === "hugodouard") return "🚗 Hugodouard";
  if (assignment.vehicleId === "paul-pot") return "🚙 Paul Pot";
  return "🥾 À pied / autre";
}
function renderAssignment(lifecycle, status = null, error = false) {
  const current = choiceKey(lifecycle.assignment.mode, lifecycle.assignment.vehicleId);
  document.querySelectorAll("#assignment-choices button").forEach(button => {
    const selected = button.dataset.assignment === current;
    button.classList.toggle("on", selected);
    button.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  $("me-car").textContent = assignmentLabel(lifecycle.assignment);
  if (status != null) {
    $("assignment-status").textContent = status;
    $("assignment-status").classList.toggle("err", error);
    $("assignment-status").classList.toggle("ok", !!status && !error);
  }
}
function setAssignmentButtonsDisabled(disabled) {
  document.querySelectorAll("#assignment-choices button").forEach(button => {
    button.disabled = disabled;
  });
}
async function changeAssignment(lifecycle, person, key) {
  if (!lifecycle.active || activeDashboard !== lifecycle) return;
  const choice = ASSIGNMENT_CHOICES[key];
  const sameChoice = choiceKey(lifecycle.assignment.mode, lifecycle.assignment.vehicleId) === key;
  if (!choice || (sameChoice && lifecycle.assignmentReady)) return;

  // Aucun point ne doit être associé pendant la petite fenêtre où l'événement
  // d'affectation n'est pas encore durablement rangé dans la file locale.
  lifecycle.assignmentReady = false;
  lifecycle.position.suspend();
  $("add-photos").disabled = true;
  setAssignmentButtonsDisabled(true);
  renderAssignment(lifecycle, "enregistrement du choix…");
  const next = makeAssignment(person, lifecycle.sessionId, choice, "user-change");
  try {
    await enqueueOutbox({
      id: `assignment:${next.assignmentId}`,
      kind: "assignment",
      assignment: next,
    });
    if (!lifecycle.active || activeDashboard !== lifecycle) return;
    lifecycle.assignment = next;
    lifecycle.assignmentReady = true;
    saveAssignmentChoice(lifecycle.personId, next);
    renderAssignment(lifecycle, next.mode === "paused"
      ? "GPS en pause — aucun point n'est enregistré"
      : "choix mémorisé jusqu'à ton prochain changement");
    lifecycle.position.assignmentChanged();
  } catch (e) {
    if (!lifecycle.active || activeDashboard !== lifecycle) return;
    renderAssignment(lifecycle,
      `choix non enregistré — GPS arrêté : ${e.message || e}`, true);
  } finally {
    if (lifecycle.active && activeDashboard === lifecycle) {
      setAssignmentButtonsDisabled(false);
      $("add-photos").disabled = !lifecycle.assignmentReady;
    }
  }
}
function initAssignmentButtons(lifecycle, person) {
  // Un changement de personne peut interrompre un enqueue pendant que les
  // boutons de l'ancien dashboard sont désactivés : toujours repartir propre.
  setAssignmentButtonsDisabled(false);
  document.querySelectorAll("#assignment-choices button").forEach(button => {
    button.onclick = () => changeAssignment(lifecycle, person, button.dataset.assignment);
  });
  renderAssignment(lifecycle);
}

async function start() {
  cleanupDashboard();
  const generation = ++startGeneration;
  const person = me;
  $("pick").classList.add("hidden");   // pas de flash de l'écran des prénoms
  let authenticated = false;
  try { authenticated = await requireAuth(generation); } // mot de passe équipage (une fois)
  catch (e) {
    if (generation === startGeneration) {
      showLogin(generation);
      $("pw-err").innerHTML = `<span class="err">Firebase indisponible — vérifie la connexion</span>`;
    }
    return;
  }
  if (!authenticated || generation !== startGeneration || me !== person || !CREW[person]) return;

  const personId = personIdFor(person);
  const sessionId = `ses-${personId}-${Date.now()}-${randomToken()}`;
  const choice = loadAssignmentChoice(personId);
  const lifecycle = {
    active: true,
    person,
    personId,
    sessionId,
    assignment: makeAssignment(person, sessionId, choice, "session-start"),
    assignmentReady: false,
    pointSeq: 0,
    statsTimer: null,
    ageTimer: null,
    photoUnsub: null,
    position: null,
  };
  activeDashboard = lifecycle;

  $("login").classList.add("hidden");
  $("dash").classList.remove("hidden");
  $("assignment-status").textContent = "";
  $("assignment-status").className = "assignment-status";
  $("up-status").textContent = "";
  $("add-photos").disabled = true;
  $("live-card").className = "card live-card waiting";
  $("pos-title").textContent = "Préparation du GPS…";
  $("pos-sub").textContent = "ton choix de déplacement décide du partage";
  $("me-name").textContent = person;
  const face = FACES[person];
  if (face) $("me-face").src = face; else $("me-face").removeAttribute("src");
  $("switch").onclick = () => {
    ++startGeneration;
    cleanupDashboard();
    clearMe(); me = null;
    renderPick();
    $("dash").classList.add("hidden"); $("pick").classList.remove("hidden");
  };
  initAssignmentButtons(lifecycle, person);
  lifecycle.position = initPosition(lifecycle, person);
  initStats(lifecycle, person);
  initPhotos(lifecycle, person);
  watchMyPhotos(lifecycle, person);

  try {
    await enqueueOutbox({
      id: `assignment:${lifecycle.assignment.assignmentId}`,
      kind: "assignment",
      assignment: lifecycle.assignment,
    });
    if (!lifecycle.active || activeDashboard !== lifecycle) return;
    lifecycle.assignmentReady = true;
    $("add-photos").disabled = false;
    saveAssignmentChoice(personId, lifecycle.assignment);
    renderAssignment(lifecycle, lifecycle.assignment.mode === "paused"
      ? "GPS en pause — choisis une voiture ou À pied / autre"
      : "choix restauré et mémorisé");
    lifecycle.position.assignmentChanged();
    scheduleOutboxFlush(0);
  } catch (e) {
    if (lifecycle.active && activeDashboard === lifecycle) {
      renderAssignment(lifecycle, `stockage local indisponible : ${e.message || e}`, true);
      lifecycle.position.showError("Trajet non démarré", "impossible de sécuriser les points hors ligne");
    }
  }
}

// ---- position v2 : active sauf en Pause -----------------------------------
function optionalMetric(value, min, max) {
  return typeof value === "number" && Number.isFinite(value)
    && value >= min && value <= max ? value : null;
}
function optionalHeading(value) {
  if (value === 360) return 0;
  return typeof value === "number" && Number.isFinite(value)
    && value >= 0 && value < 360 ? value : null;
}
function initPosition(lifecycle, person) {
  let lastQueuedAt = 0;
  let lastQueuedPoint = null;
  let queueInFlight = false;
  let lastSentPoint = null;
  let sentAt = 0;
  let webWatchId = null;
  let nativeWatchId = null;
  let nativeGeo = null;
  let watchGeneration = 0;
  const card = $("live-card");
  const setState = (cls, title, sub) => {
    if (!lifecycle.active || activeDashboard !== lifecycle) return;
    card.className = "card live-card " + cls;
    $("pos-title").textContent = title;
    if (sub != null) $("pos-sub").innerHTML = sub;
  };
  // rafraîchit le "envoyée il y a X" toutes les 10 s
  lifecycle.ageTimer = setInterval(() => {
    if (!sentAt || lifecycle.assignment.mode === "paused" || !lastSentPoint) return;
    const s = Math.round((Date.now() - sentAt) / 1000);
    const t = s < 60 ? `${s}s` : `${Math.round(s / 60)} min`;
    $("pos-sub").textContent = `capturée il y a ${t} · ${lastSentPoint.lat.toFixed(4)}, ${lastSentPoint.lng.toFixed(4)}`;
  }, 10000);

  const queuePosition = async position => {
    if (!lifecycle.active || activeDashboard !== lifecycle || !lifecycle.assignmentReady) return;
    const assignment = lifecycle.assignment;
    if (assignment.mode === "paused") return;
    const coords = position && position.coords;
    if (!coords || !validCoords(coords.latitude, coords.longitude)) {
      setState("err", "GPS incohérent", "coordonnées ignorées");
      return;
    }
    const lat = coords.latitude, lng = coords.longitude;
    const rawAccuracyM = typeof coords.accuracy === "number" && Number.isFinite(coords.accuracy)
      ? coords.accuracy : null;
    if (rawAccuracyM != null && rawAccuracyM > 250) {
      setState("waiting", "Signal GPS trop imprécis",
        `${Math.round(rawAccuracyM)} m de précision · attente d'un meilleur signal`);
      return;
    }
    const accuracyM = optionalMetric(rawAccuracyM, 0, 250);
    if (queueInFlight) return;
    const now = Date.now();
    const elapsed = now - lastQueuedAt;
    // Comparer au dernier point ENREGISTRÉ, pas au callback précédent : sinon
    // une marche faite de petits deltas serait prise à tort pour de l'immobilité.
    const moved = !lastQueuedPoint || dist(lastQueuedPoint, [lat, lng]) > 25;
    // Minimum ABSOLU de 60 s : avec neuf téléphones et une journée de route
    // réaliste, les deux écritures v2 par point gardent une marge de quota.
    // À l'arrêt, un point de rappel toutes les cinq minutes suffit.
    if (lastQueuedAt && (elapsed < 60000 || (!moved && elapsed < 300000))) return;

    const capturedAtMs = Number.isFinite(position.timestamp) && position.timestamp > 0
      ? Math.round(position.timestamp) : now;
    const pointId = `${lifecycle.sessionId}-${String(++lifecycle.pointSeq).padStart(6, "0")}-${capturedAtMs}`;
    const point = {
      pointId,
      tripId: TRIP_ID,
      personId: lifecycle.personId,
      displayName: person,
      vehicleId: assignment.vehicleId,
      mode: assignment.mode,
      assignmentId: assignment.assignmentId,
      sessionId: lifecycle.sessionId,
      deviceId: DEVICE_ID,
      lat,
      lng,
      capturedAtMs,
      accuracyM,
      speedMps: optionalMetric(coords.speed, 0, 200),
      headingDeg: optionalHeading(coords.heading),
    };
    queueInFlight = true;
    try {
      await enqueueOutbox({ id: `point:${pointId}`, kind: "point", point });
      if (lifecycle.assignment.assignmentId === assignment.assignmentId) {
        lastQueuedAt = now;
        lastQueuedPoint = [lat, lng];
        setState("waiting", "Position sécurisée localement",
          `envoi en cours · ${lat.toFixed(4)}, ${lng.toFixed(4)}`);
      }
    } catch (e) {
      setState("err", "Position non sauvegardée", `${e.message || e}`);
    } finally { queueInFlight = false; }
  };

  const clearWatcher = () => {
    ++watchGeneration;
    if (webWatchId != null && navigator.geolocation) {
      navigator.geolocation.clearWatch(webWatchId);
      webWatchId = null;
    }
    if (nativeWatchId != null && nativeGeo) {
      const id = nativeWatchId;
      nativeWatchId = null;
      Promise.resolve(nativeGeo.clearWatch({ id })).catch(() => {});
    }
  };
  const startWatcher = async () => {
    clearWatcher();
    if (!lifecycle.active || !lifecycle.assignmentReady
        || lifecycle.assignment.mode === "paused") return;
    const myWatchGeneration = watchGeneration;
    setState("waiting", "Activation du GPS…",
      "ta position est partagée pendant que l'app est ouverte");
    if (native) {
      nativeGeo = plugin("Geolocation");
      if (!nativeGeo) return setState("err", "GPS non disponible", "plugin natif absent");
      try { await nativeGeo.requestPermissions(); } catch (_) {}
      if (!lifecycle.active || myWatchGeneration !== watchGeneration
          || lifecycle.assignment.mode === "paused") return;
      try {
        // Après un changement de voiture, ne jamais ré-étiqueter un fix mis en
        // cache sous l'ancienne affectation : le premier point doit être frais.
        const id = await nativeGeo.watchPosition({ enableHighAccuracy: true, maximumAge: 0,
          timeout: 20000 }, (pos, err) => {
          if (!lifecycle.active || myWatchGeneration !== watchGeneration) return;
          if (err || !pos) return setState("err", "GPS indisponible",
            (err && err.message) || "autorise la localisation");
          queuePosition(pos);
        });
        if (!lifecycle.active || myWatchGeneration !== watchGeneration
            || lifecycle.assignment.mode === "paused") {
          Promise.resolve(nativeGeo.clearWatch({ id })).catch(() => {});
        } else nativeWatchId = id;
      } catch (e) {
        if (myWatchGeneration === watchGeneration) {
          setState("err", "GPS indisponible", e.message || "autorise la localisation");
        }
      }
    } else if (navigator.geolocation) {
      webWatchId = navigator.geolocation.watchPosition(
        position => {
          if (lifecycle.active && myWatchGeneration === watchGeneration) queuePosition(position);
        },
        e => {
          if (myWatchGeneration === watchGeneration) {
            setState("err", "GPS refusé", `autorise la localisation (${e.code})`);
          }
        },
        { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 });
    } else setState("err", "GPS non disponible", "");
  };

  return {
    stop: clearWatcher,
    suspend: clearWatcher,
    assignmentChanged() {
      lastQueuedAt = 0;
      lastQueuedPoint = null;
      if (lifecycle.assignment.mode === "paused") {
        clearWatcher();
        setState("paused", "Partage en pause", "aucun point GPS n'est enregistré");
      } else startWatcher();
    },
    markSent(point) {
      if (point.personId !== lifecycle.personId || point.sessionId !== lifecycle.sessionId) return;
      sentAt = point.capturedAtMs;
      lastSentPoint = point;
      setState("live", "Position à jour ✓",
        `envoyée · ${point.lat.toFixed(4)}, ${point.lng.toFixed(4)}`);
    },
    markQueued(error) {
      if (lifecycle.assignment.mode === "paused") return;
      setState("waiting", "Envoi en attente",
        `trajet gardé sur ce téléphone · ${error.code || error.message || error}`);
    },
    showError(title, sub) { setState("err", title, sub); },
  };
}

function dist(a, b) { // mètres, approx équirectangulaire
  const k = Math.cos(a[0] * Math.PI / 180), R = 6371000, r = Math.PI / 180;
  const dx = (b[1] - a[1]) * k * r, dy = (b[0] - a[0]) * r;
  return Math.sqrt(dx * dx + dy * dy) * R;
}

// ---- PV / XP (sauvegarde automatique à chaque modification) ----------------
function initStats(lifecycle, person) {
  const pv = $("pv"), pvVal = $("pv-val");
  pv.value = 5;
  pvVal.textContent = "5";
  $("stats-status").textContent = "chargement…";
  pv.oninput = () => {
    pvVal.textContent = pv.value;
    clearTimeout(lifecycle.statsTimer);
    $("stats-status").textContent = "…";
    const value = +pv.value;
    lifecycle.statsTimer = setTimeout(async () => {
      try {
        const { db, doc, setDoc, ts } = await fb();
        await setDoc(doc(db, "crew", person),
          { name: person, car: CREW[person], pv: value, at: ts() }, { merge: true });
        if (!lifecycle.active || activeDashboard !== lifecycle) return;
        $("stats-status").innerHTML = `<span class="ok">enregistré ✓</span>`;
      } catch (e) {
        if (lifecycle.active && activeDashboard === lifecycle) {
          $("stats-status").innerHTML = `<span class="err">${e.code || e}</span>`;
        }
      }
    }, 500);   // léger délai pour ne pas écrire à chaque cran du curseur
  };

  // charge mes PV déjà enregistrés
  (async () => {
    try {
      const { db, doc, getDoc } = await fb();
      const snap = await getDoc(doc(db, "crew", person));
      if (!lifecycle.active || activeDashboard !== lifecycle) return;
      if (snap.exists() && snap.data().pv != null) {
        pv.value = snap.data().pv; pvVal.textContent = snap.data().pv;
        $("stats-status").textContent = "enregistré automatiquement";
      }
    } catch (_) {}
  })();
}

// ---- photos (localisation gardée) -----------------------------------------
function mediaCapturedAt(value, fallback = Date.now()) {
  if (value instanceof Date && Number.isFinite(value.getTime())) return value.getTime();
  if (typeof value === "number" && Number.isFinite(value) && value > 0) return value;
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const midday = Date.parse(`${value}T12:00:00Z`);
    if (Number.isFinite(midday)) return midday;
  }
  const parsed = typeof value === "string" ? Date.parse(value) : NaN;
  return Number.isFinite(parsed) ? parsed : fallback;
}
function snapshotMediaContext(lifecycle, person, capturedAtMs = Date.now()) {
  const assignment = lifecycle.assignment;
  return {
    lifecycle,
    tripId: TRIP_ID,
    personId: lifecycle.personId,
    displayName: person,
    vehicleId: assignment.vehicleId,
    mode: assignment.mode,
    assignmentId: assignment.assignmentId,
    capturedAtMs,
  };
}
function currentUploadStatus(context, html, asText = false) {
  const lifecycle = context && context.lifecycle;
  if (!lifecycle || !lifecycle.active || activeDashboard !== lifecycle) return;
  if (asText) $("up-status").textContent = html;
  else $("up-status").innerHTML = html;
}
// Relit la video que le plugin natif a copiee en cache. C'est l'etape la plus
// fragile du chemin video : selon la version de Capacitor et le schema de la
// WebView, l'URL servable n'est pas la meme, et un echec ici remonte comme un
// « Failed to fetch » indistinguable de celui de l'upload Cloudinary. On essaie
// donc les formes connues, et on rapporte precisement ce qui a echoue.
async function readLocalVideo(path, bytes) {
  const poids = bytes ? ` (${Math.round(bytes / 1048576)} Mo)` : "";
  const bare = String(path).replace(/^file:\/\//, "");
  const tries = [];
  if (CAP && CAP.convertFileSrc) tries.push(["convertFileSrc", CAP.convertFileSrc(path)]);
  tries.push(["schéma WebView", `${location.origin}/_capacitor_file_${bare}`]);
  tries.push(["chemin brut", path]);
  const seen = new Set(), errs = [];
  for (const [label, url] of tries) {
    if (seen.has(url)) continue;
    seen.add(url);
    try {
      const r = await fetch(url);
      if (!r.ok) { errs.push(`${label}: HTTP ${r.status}`); continue; }
      const blob = await r.blob();
      if (!blob.size) { errs.push(`${label}: fichier vide`); continue; }
      return blob;
    } catch (e) {
      errs.push(`${label}: ${e && e.message ? e.message : e}`);
    }
  }
  throw new Error(`lecture de la vidéo${poids} impossible — ` + errs.join(" | "));
}

function initPhotos(lifecycle, person) {
  let pendingBrowserContext = null;
  $("add-photos").onclick = async () => {
    if (!lifecycle.assignmentReady) {
      $("up-status").innerHTML = '<span class="err">choisis d’abord ton mode de déplacement</span>';
      return;
    }
    const baseContext = snapshotMediaContext(lifecycle, person);
    // natif (APK) : le plugin AfricaMedia lit le GPS EXIF grâce à
    // ACCESS_MEDIA_LOCATION. sinon (navigateur) : <input file> + EXIF en JS.
    if (native) {
      try {
        const mediaPlugin = plugin("AfricaMedia");
        if (!mediaPlugin) throw new Error("sélecteur natif indisponible");
        const { items } = await mediaPlugin.pickWithLocation();
        for (const it of (items || [])) {
          const lat = it.lat ?? null, lng = it.lng ?? null, date = it.date || null;
          const context = {
            ...baseContext,
            capturedAtMs: mediaCapturedAt(it.capturedAt || date, baseContext.capturedAtMs),
          };
          if (it.video && it.path) {
            // vidéo : le natif a copié le fichier en cache (pas de base64) ->
            // on le relit via la WebView avant de l'uploader. La WebView doit
            // la charger ENTIÈREMENT en mémoire : au-delà du plafond, on refuse
            // ici plutôt que d'échouer sur un fetch sans explication.
            if (it.bytes && it.bytes > MAX_VIDEO_BYTES) {
              currentUploadStatus(context,
                `<span class="err">vidéo trop lourde (${Math.round(it.bytes / 1048576)} Mo, max `
                + `${Math.round(MAX_VIDEO_BYTES / 1048576)}) — filme plus court</span>`);
              continue;
            }
            const blob = await readLocalVideo(it.path, it.bytes);
            await uploadPhoto(blob, lat, lng, date, true, context);
          } else {
            await uploadPhoto(b64toBlob(it.base64), lat, lng, date, false, context);
          }
        }
      } catch (e) {
        currentUploadStatus(baseContext, `<span class="err">erreur: ${e.message || e}</span>`);
      }
    } else {
      pendingBrowserContext = baseContext;
      $("fallback-input").click();
    }
  };
  $("fallback-input").onchange = async e => {
    const baseContext = pendingBrowserContext || snapshotMediaContext(lifecycle, person);
    pendingBrowserContext = null;
    for (const f of [...e.target.files]) {
      let lat = null, lng = null, date = null;
      let capturedAtMs = mediaCapturedAt(f.lastModified, baseContext.capturedAtMs);
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
          if (d && d.DateTimeOriginal) {
            capturedAtMs = mediaCapturedAt(d.DateTimeOriginal, capturedAtMs);
            date = new Date(capturedAtMs).toISOString().slice(0, 10);
          }
        } catch (_) {}
      }
      await uploadPhoto(f, lat, lng, date, video,
        { ...baseContext, capturedAtMs });
    }
    e.target.value = "";
  };
}

async function uploadPhoto(blob, lat, lng, date, video = isVideoBlob(blob), context) {
  if (!context || !context.personId || !context.assignmentId) {
    throw new Error("contexte du média absent");
  }
  const noun = video ? "vidéo" : "photo";
  if (video && blob.size > MAX_VIDEO_BYTES) {
    currentUploadStatus(context,
      `<span class="err">vidéo trop lourde (${Math.round(blob.size / 1048576)} Mo, max 100) — filme plus court</span>`);
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
  currentUploadStatus(context, "envoi…", true);
  try {
    // le FICHIER va sur Cloudinary (gratuit, sans carte) ; seules les
    // MÉTADONNÉES (nom, position, date, url, type) vont dans Firestore.
    // Endpoint distinct pour la vidéo (/video/upload) vs l'image (/image/upload).
    const form = new FormData();
    form.append("file", blob);
    form.append("upload_preset", CLOUDINARY.preset);
    let res;
    try {
      res = await fetch(
        `https://api.cloudinary.com/v1_1/${CLOUDINARY.cloudName}/${video ? "video" : "image"}/upload`,
        { method: "POST", body: form });
    } catch (e) {
      // fetch qui echoue sans reponse = reseau coupe ou envoi interrompu. Le
      // distinguer d'une erreur de lecture du fichier evite de chercher au
      // mauvais endroit la prochaine fois.
      throw new Error(`envoi vers Cloudinary interrompu (${Math.round(blob.size / 1048576)} Mo) — `
        + `réseau instable ? détail : ${e && e.message ? e.message : e}`);
    }
    if (!res.ok) {
      let why = "";
      try { why = " — " + ((await res.json()).error || {}).message; } catch (_) {}
      throw new Error(`Cloudinary a refusé le ${noun} (HTTP ${res.status})${why}`);
    }
    const link = (await res.json()).secure_url;

    const { db, addDoc, collection, ts } = await fb();
    await addDoc(collection(db, "photos"), {
      // Champs historiques conservés pour l'ancien site.
      name: context.displayName,
      car: legacyCar(context),
      url: link,
      type: video ? "video" : "image",
      lat: located ? lat : null, lng: located ? lng : null,
      gps: located && !manual, manual: located && manual,
      date: date || new Date(context.capturedAtMs).toISOString().slice(0, 10),
      at: ts(),
      // Métadonnées v2 : identité stable et contexte réel au moment du média.
      tripId: TRIP_ID,
      personId: context.personId,
      displayName: context.displayName,
      vehicleIdAtCapture: context.vehicleId,
      mode: context.mode,
      assignmentId: context.assignmentId,
      capturedAt: new Date(context.capturedAtMs),
      locationSource: located ? (manual ? "manual" : "media-gps") : "none",
    });
    // la grille "mes photos" se met à jour toute seule (onSnapshot)
    currentUploadStatus(context, manual
      ? `<span class="ok">${noun} ajoutée à l'endroit choisi ✓</span>`
      : located
        ? `<span class="ok">${noun} ajoutée avec sa position ✓</span>`
        : locationError
          ? `<span class="ok">${noun} ajoutée</span> (carte indisponible → ajoute le lieu plus tard)`
          : `<span class="ok">${noun} ajoutée</span> (sans lieu → n'apparaîtra pas sur la carte)`);
  } catch (e) {
    currentUploadStatus(context, `<span class="err">erreur: ${e.code || e}</span>`);
  }
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
      // Ne crée pas un document « à moitié v2 » lors de l'édition d'un ancien
      // média ; les médias v2 gardent en revanche leur provenance cohérente.
      if (d.tripId === TRIP_ID && d.personId) patch.locationSource = "manual";
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

async function watchMyPhotos(lifecycle, person) {
  const { db, collection, query, where, onSnapshot } = await fb();
  if (!lifecycle.active || activeDashboard !== lifecycle) return;
  initMediaModal();
  document.querySelectorAll("#mediafilter button").forEach(b => {
    b.onclick = () => {
      if (!lifecycle.active || activeDashboard !== lifecycle) return;
      mediaFilter = b.dataset.f;
      document.querySelectorAll("#mediafilter button").forEach(x => x.classList.toggle("on", x === b));
      renderMyPhotos();
    };
  });
  const unsubscribe = onSnapshot(query(collection(db, "photos"), where("name", "==", person)), snap => {
    if (!lifecycle.active || activeDashboard !== lifecycle) return;
    myDocs = [];
    snap.forEach(d => myDocs.push({ id: d.id, ...d.data() }));
    // récent d'abord : par date puis par horodatage d'envoi
    myDocs.sort((a, b) => (b.date || "").localeCompare(a.date || "") || atMs(b) - atMs(a));
    renderMyPhotos();
  }, e => {
    if (lifecycle.active && activeDashboard === lifecycle) {
      $("up-status").innerHTML = `<span class="err">${e.code || e}</span>`;
    }
  });
  if (!lifecycle.active || activeDashboard !== lifecycle) unsubscribe();
  else lifecycle.photoUnsub = unsubscribe;
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
renderPick();
if (me && CREW[me]) {
  saveMe(me);
  start();
} else {
  if (me) clearMe();
  me = null;
}
