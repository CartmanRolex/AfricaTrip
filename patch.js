const fs = require('fs');
let html = fs.readFileSync('src/template.html', 'utf8');

html = html.replace(
  `legLine.setStyle({color:DIFF_COLOR(legMeta(P.legIdx).diff)});`,
  `legLine.setStyle({color:DIFF_COLOR(legMeta(P.legIdx).diff)});
  
  // Update background route to only show future
  routeLine.setLatLngs(routeSlice(currentTripProgressKm(), totalKm));`
);

fs.writeFileSync('src/template.html', html);
