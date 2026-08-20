/**
 * Precalcule les RECOLLAGES DE ROUTE et les ecrit dans src/tweens.json.
 *
 *   node src/collect_tweens.mjs        # ecrit src/tweens.json
 *
 * Pourquoi ce fichier existe
 * --------------------------
 * Entre deux points GPS, le site cherche une geometrie deja routee qui les
 * relie (`chercherTween`). Cette recherche projetait chaque paire sur les 1219
 * geometries du cache — 60 900 sommets — meme celles situees a 2000 km. Mesure
 * sur un seul rendu : **85,6 millions d'appels a `hav()` et 4,9 s de
 * processeur**, soit 14 s de chargement sur un telephone.
 *
 * Or le resultat ne depend que de la paire et du cache de routes : il est
 * IDENTIQUE chez tous les visiteurs, et il tient en 250 entrees, 11 Ko. Chaque
 * navigateur refaisait donc le meme calcul pour aboutir au meme fichier.
 *
 * Pourquoi ce n'etait pas deja fait en Python
 * -------------------------------------------
 * `fetch_routes.py` refuse — a raison — de reimplementer la reconstruction du
 * front-end (bucketing a la minute, rejet des transitions impossibles, traces
 * partagees entre occupants) : cette copie pourrirait a la premiere
 * modification du template. Il DEVINE donc les paires utiles, et celles qu'il
 * rate tombaient dans la recherche cote client.
 *
 * La prudence etait juste, la conclusion etait fausse. On n'a pas a choisir
 * entre dupliquer la logique et laisser le client calculer : on fait tourner
 * LE VRAI SITE, sans ecran. Le code qui produit la table est le code qui
 * dessine, ils ne peuvent donc pas diverger.
 *
 * Ce qui est stocke
 * -----------------
 * Un recollage est toujours « ce morceau de cette geometrie », donc
 * `[cle, i0, i1]` suffit — 11 Ko au lieu de 18 si on embarquait les
 * coordonnees. Les paires SANS reponse sont memorisees a `null` : sans ca, le
 * site relancerait la recherche complete pour elles a chaque fois.
 */
import puppeteer from '../node_modules/puppeteer/lib/esm/puppeteer/puppeteer.js';
import fs from 'node:fs';

const PAGE = new URL('../index.html', import.meta.url).href;
const SORTIE = new URL('./tweens.json', import.meta.url).pathname;

const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });
const page = await browser.newPage();
const erreurs = [];
page.on('pageerror', e => erreurs.push(e.message));
await page.goto(PAGE, { waitUntil: 'load' });
await new Promise(r => setTimeout(r, 9000));   // laisser l'instantane se poser

const table = await page.evaluate(async () => {
  // On repart de zero : sinon la table deja embarquee repondrait a notre place
  // et on ne collecterait que ce qu'on savait deja.
  TWEENS.clear();
  tweenCache.clear();
  const vus = {};
  const brut = chercherTween;
  window.chercherTween = (a, b) => {
    const ref = brut(a, b);
    vus[`${a[0].toFixed(4)},${a[1].toFixed(4)};${b[0].toFixed(4)},${b[1].toFixed(4)}`] = ref;
    return ref;
  };

  // Parcourir ce qu'un visiteur peut demander : chaque sujet, chaque jour.
  const sujets = ['vehicle:hugodouard', 'vehicle:paul-pot',
    ...CAR1.concat(CAR2).map(n => 'person:' + slug(n))];
  const dernier = REC.findIndex(r => r.iso === TODAY_ISO);
  for (const s of sujets) {
    setTrackSubject(s, false);
    for (let i = 0; i <= (dernier < 0 ? REC.length - 1 : dernier); i++) {
      setIndex(i);
      await new Promise(r => setTimeout(r, 0));
    }
  }
  window.chercherTween = brut;
  return vus;
});

await browser.close();

const n = Object.keys(table).length;
const vides = Object.values(table).filter(v => !v).length;
if (erreurs.length) {
  console.log('Erreurs de page :');
  erreurs.slice(0, 5).forEach(e => console.log('  ' + e));
}
// Une table vide signifierait que la collecte a echoue, pas qu'il n'y a rien a
// recoller. On refuse alors d'ecraser celle qui marche.
if (!n) {
  console.log('Aucun recollage collecte — tweens.json laisse intact.');
  process.exit(erreurs.length ? 1 : 0);
}
fs.writeFileSync(SORTIE, JSON.stringify(table));
const ko = fs.statSync(SORTIE).size / 1024;
console.log(`${n} recollages (${n - vides} resolus, ${vides} sans reponse) -> `
  + `src/tweens.json, ${ko.toFixed(0)} Ko`);
console.log('Lancer ensuite : python src/build.py');
if (erreurs.length) process.exit(1);
