const fs = require('fs');
let text = fs.readFileSync('data/Config.csv', 'utf8');

text = text.replace(
`ABIDJAN,Abidjan,,,,,
ACCRA,Accra,,,,,
LOMÉ,Lomé,,,,,`,
`FREETOWN,Freetown,,,,,`
);

text = text.replace(
`Kissidougou,9.185,-10.100,,,,
Nzérékoré,7.756,-8.818,,,,
Man,7.412,-7.554,,,,
Yamoussoukro,6.816,-5.274,,,,
Abidjan,5.345,-4.024,ABIDJAN,,,
Takoradi,4.898,-1.760,,,,
Accra,5.603,-0.187,ACCRA,,,
Lomé,6.130,1.216,LOMÉ,,,`,
`Freetown,8.484,-13.234,FREETOWN,,,`
);

fs.writeFileSync('data/Config.csv', text);
