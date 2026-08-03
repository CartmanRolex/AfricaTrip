const fs = require('fs');
let text = fs.readFileSync('data/AfriqueCalendrier_-_Presences_Voyage.csv', 'utf8');

text = text.replace('Jeu 18 sept.,ABIDJAN,?', 'Jeu 18 sept.,FREETOWN,?');
text = text.replace('Jeu 25 sept.,ACCRA,?', 'Jeu 25 sept.,,?');
text = text.replace('Dim 28 sept.,LOMÉ,?', 'Dim 28 sept.,,?');

fs.writeFileSync('data/AfriqueCalendrier_-_Presences_Voyage.csv', text);
