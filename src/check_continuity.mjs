/**
 * Vérifie L'INVARIANT DU TRACÉ sur index.html, tous sujets × tous jours :
 *
 *     la ligne ne se coupe QUE là où la donnée se coupe.
 *
 * Deux ruptures sont légitimes, et deux seulement :
 *   1. `trackSegments()` a ouvert une section (transition impossible > 6 h) ;
 *   2. le sujet n'est pas encore parti — sa position du moment n'a rien à voir
 *      avec son embarquement, on ne relie donc pas les deux.
 *
 * Toute autre coupure est un défaut d'affichage : on savait relier et on ne
 * l'a pas fait. Le trait doit se dégrader par paliers — route exacte, route
 * recollée depuis le cache, segment droit — mais jamais casser.
 *
 * Pourquoi ce fichier existe : les trous ont été corrigés un par un pendant des
 * jours, chaque correction en laissant d'autres. Le test qui les surveillait ne
 * regardait que deux jonctions précises et annonçait « aucun trou » alors que
 * 39 jours-sujets étaient coupés. Un invariant vérifié partout remplace cette
 * chasse au symptôme.
 *
 *   node src/check_continuity.mjs        # sort en code 1 si l'invariant casse
 */
import puppeteer from '../node_modules/puppeteer/lib/esm/puppeteer/puppeteer.js';

const PAGE = new URL('../index.html', import.meta.url).href;
const TOL_KM = 1;        // deux bouts à moins d'1 km sont considérés joints

const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });
const page = await browser.newPage();
const erreurs = [];
page.on('pageerror', e => erreurs.push(e.message));
await page.goto(PAGE, { waitUntil: 'load' });
await new Promise(r => setTimeout(r, 9000));   // laisser Firebase répondre

const rapport = await page.evaluate(async (TOL) => {
  const anomalies = [];
  let controles = 0;
  const dernierJour = REC.findIndex(r => r.iso === TODAY_ISO);
  const sujets = ['vehicle:hugodouard', 'vehicle:paul-pot',
    ...CAR1.concat(CAR2).map(n => 'person:' + slug(n))];

  for (const sujet of sujets) {
    setTrackSubject(sujet, false);
    const [kind, id] = sujet.split(':');
    const nom = kind === 'person' ? NAME_BY_ID.get(id) : null;

    for (let i = 0; i <= dernierJour; i++) {
      setIndex(i);
      await new Promise(r => setTimeout(r, 50));
      controles++;

      // la ligne DU SUJET : trait plein + pointillés. Les traces de fond des
      // voitures (weight 3) sont d'autres lignes, légitimement séparées.
      const morceaux = [];
      actualTrackLayer.eachLayer(l => {
        const o = l.options || {};
        if (l.getLatLngs && (o.weight === 5 || o.dashArray)) morceaux.push(l.getLatLngs());
      });
      if (morceaux.length < 2) continue;

      // une chaîne bien formée n'a que deux bouts libres : son début et sa fin
      const bouts = morceaux.flatMap((ll, k) => [{ k, pt: ll[0] }, { k, pt: ll.at(-1) }]);
      const libres = bouts.filter(a =>
        !bouts.some(x => x.k !== a.k && hav(a.pt, x.pt) <= TOL));
      const coupures = Math.max(0, (libres.length - 2) / 2);
      if (!coupures) continue;

      // combien de ruptures sont légitimes ?
      const pts = kind === 'person' ? personPoints(nom) : vehiclePoints(id);
      const ruptures = Math.max(0, trackSegments(pts).length - 1);
      const pasParti = kind === 'person' && !onboardAt(nom, i);
      const permises = ruptures + (pasParti ? 1 : 0);

      if (coupures > permises)
        anomalies.push({ sujet: id, jour: REC[i].iso, coupures, permises });
    }
  }
  return { controles, anomalies };
}, TOL_KM);

await browser.close();

console.log(`${rapport.controles} combinaisons sujet × jour contrôlées`);
if (erreurs.length) {
  console.log('\nErreurs de page :');
  erreurs.slice(0, 5).forEach(e => console.log('  ' + e));
}
if (rapport.anomalies.length) {
  console.log(`\nINVARIANT CASSÉ — ${rapport.anomalies.length} coupure(s) inexpliquée(s) :`);
  for (const a of rapport.anomalies.slice(0, 15))
    console.log(`  ${a.sujet} ${a.jour} : ${a.coupures} coupure(s), ${a.permises} légitime(s)`);
  process.exit(1);
}
if (erreurs.length) process.exit(1);
console.log('\nInvariant respecté : la ligne ne se coupe que là où la donnée se coupe.');
