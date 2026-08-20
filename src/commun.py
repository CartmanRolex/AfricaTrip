"""
Les calculs de base, ecrits UNE SEULE FOIS.

Trois notions elementaires — la distance entre deux points, la voiture d'un
releve, la lecture d'une date — etaient recopiees dans quatre scripts. Ce n'est
pas une question d'elegance : une copie corrigee laisse les autres fausses, et
c'est arrive pour de vrai.

Deux exemples mesures dans ce depot :

* `check_overrides.py` lisait les dates SANS fuseau. Chaque date de media s'en
  trouvait decalee de deux heures — soit environ 180 km quand la voiture roule
  — et le controle comparait donc les medias aux points GPS du mauvais moment.
  Le meme defaut, dans une autre copie, avait donne 45 km d'erreur mediane sur
  les positions devinees, avec un symptome trompeur : l'erreur ne diminuait pas
  quand le point de trace se rapprochait, ce qui est physiquement impossible.
* La distance existait en deux versions aux signatures differentes
  (`hav` sur des dictionnaires, `hav_km` sur des couples), donc impossibles a
  corriger ensemble.

Ce module ne couvre que le cote Python. Le site (`template.html`) et l'appli
(`app/www/app.js`) tournent dans un navigateur et ne peuvent pas l'importer :
on ne partage pas du code entre Python et JavaScript. C'est pourquoi
`src/check_accord.py` verifie que les deux mondes donnent bien la meme reponse
sur les memes entrees — a defaut de partager le code, on interdit la derive.
"""
import datetime
import math

RAYON_TERRE_KM = 6371.0
UTC = datetime.timezone.utc


def coord(p):
    """Accepte {'lat':..,'lng':..} ou (lat, lng) et rend un couple de flottants.

    Les deux formes existaient dans le depot ; les accepter ici evite d'avoir
    a choisir un camp et de reecrire les appelants.
    """
    if isinstance(p, dict):
        return float(p["lat"]), float(p["lng"])
    return float(p[0]), float(p[1])


def hav_km(a, b):
    """Distance orthodromique en kilometres entre deux points."""
    la1, lo1 = coord(a)
    la2, lo2 = coord(b)
    d = math.pi / 180
    dla, dlo = (la2 - la1) * d, (lo2 - lo1) * d
    h = (math.sin(dla / 2) ** 2
         + math.cos(la1 * d) * math.cos(la2 * d) * math.sin(dlo / 2) ** 2)
    return 2 * RAYON_TERRE_KM * math.asin(math.sqrt(h))


# Les identifiants de voiture ont trois generations : le nom actuel, l'ancien
# numero (1/2) et les formes intermediaires. Tout ce qui lit une affectation
# doit passer par ici, sinon `car-1` et `hugodouard` designent deux voitures
# differentes selon le script qui regarde.
_VOITURES = {
    "hugodouard": "hugodouard", "1": "hugodouard",
    "car-1": "hugodouard", "voiture-1": "hugodouard",
    "paul-pot": "paul-pot", "paulpot": "paul-pot", "2": "paul-pot",
    "car-2": "paul-pot", "voiture-2": "paul-pot",
}


def vehicle_id(valeur):
    """Normalise une affectation de voiture, ou None si ce n'en est pas une.

    « obs » (a pied / autre, et valeur par defaut de l'appli) rend None
    volontairement : ce n'est pas une voiture.
    """
    v = str(valeur or "").strip().lower().replace(" ", "-")
    return _VOITURES.get(v)


def ms_utc(valeur):
    """Un horodatage -> millisecondes depuis 1970 en UTC, ou None.

    LE PIEGE, celui qui a coute deux bugs : `strptime` rend une date SANS
    fuseau, et `.timestamp()` l'interprete alors dans le fuseau de la machine.
    Sur une machine en heure d'ete europeenne, cela decale tout de deux heures
    — environ 180 km au rythme d'une voiture. Les horodatages du projet sont
    en UTC ; on l'ecrit donc explicitement, ici et nulle part ailleurs.

    Accepte : millisecondes (nombre), ISO `2026-08-11T15:38:05Z`, ou une date
    seule `2026-08-11` (ramenee a minuit UTC).
    """
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    if isinstance(valeur, datetime.datetime):
        d = valeur if valeur.tzinfo else valeur.replace(tzinfo=UTC)
        return d.timestamp() * 1000
    s = str(valeur).strip()
    if s.isdigit():
        return float(s)
    # D'abord la lecture complete : elle respecte les fractions de seconde et
    # un decalage explicite (`+02:00`). Sans fuseau indique, on impose UTC —
    # c'est precisement la ou les deux bugs se sont loges.
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=UTC)).timestamp() * 1000
    except ValueError:
        pass
    # Repli pour les formes que `fromisoformat` refuse (date seule, secondes
    # tronquees, texte parasite en fin de chaine).
    t = s[:19]
    if len(t) == 10:
        t += "T00:00:00"
    try:
        return (datetime.datetime.strptime(t, "%Y-%m-%dT%H:%M:%S")
                .replace(tzinfo=UTC).timestamp() * 1000)
    except ValueError:
        return None


def dt_utc(valeur):
    """Le meme que `ms_utc`, mais rendu en `datetime` conscient du fuseau.

    Certains appelants comparent des dates entre elles ; leur faire refaire la
    conversion a la main serait rouvrir la porte au bug qu'on vient de fermer.
    """
    ms = ms_utc(valeur)
    return None if ms is None else datetime.datetime.fromtimestamp(ms / 1000, UTC)


def iso_utc(ms):
    """Millisecondes -> `2026-08-11T15:38:05Z`. L'inverse de `ms_utc`."""
    if ms is None:
        return None
    return (datetime.datetime.fromtimestamp(float(ms) / 1000, UTC)
            .strftime("%Y-%m-%dT%H:%M:%SZ"))
