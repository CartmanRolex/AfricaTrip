"""
Remet la vraie date de tournage sur les videos mal datees.

Usage:  python src/fix_video_dates.py            # n'ecrit RIEN, montre le diff
        python src/fix_video_dates.py --commit   # applique

Pourquoi ce script existe
-------------------------
Une video PORTE sa date de tournage, dans les metadonnees du conteneur MP4
(atome `mvhd`). L'app Android la lit ; le repli navigateur — donc la PWA
iPhone — non : il retombe sur `lastModified`, qui est souvent l'instant ou le
fichier a ete copie juste avant l'envoi.

Consequence mesuree : quatre videos de Jehan datees du 13 aout ont ete tournees
le 11, une datee du 18 l'a ete le 14. Elles apparaissent donc au mauvais moment
de la frise, et la position choisie a la main se retrouve a des centaines de
kilometres de la voiture *a l'instant declare*. En remettant la vraie date, la
distance mediane entre le point choisi et la voiture tombe de 255 km a 59 km :
les equipiers avaient bien place leurs videos, c'est la date qui les envoyait
au mauvais endroit.

La date lue dans le fichier est un FAIT, pas une estimation. C'est la seule
chose qu'on corrige ici — les positions choisies a la main ne sont pas touchees.

Deux avertissements
-------------------
1. Les regles Firestore rendent la date IMMUABLE pour un client
   (`app/firestore.rules` : « url/auteur/date/type restent immuables »). Ce
   script passe par une cle de service, qui contourne les regles. C'est
   deliberement une operation d'administration ponctuelle, pas une porte
   ouverte : il n'ecrit que `capturedAt`/`date`, et seulement quand le fichier
   lui-meme le contredit.
2. `mvhd` ne porte pas de fuseau. Les ecarts inferieurs a `MARGE_H` sont donc
   ignores : sans certitude, on ne touche a rien.
"""
import argparse, datetime, json, os, struct, sys, urllib.error, urllib.request
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fetch_routes import fields, firebase_config, fs_list  # noqa: E402

KEY_FILE = os.path.join(HERE, "..", ".firestore-credentials.json")
SCOPE = "https://www.googleapis.com/auth/datastore"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EPOCH_MP4 = datetime.datetime(1904, 1, 1, tzinfo=datetime.timezone.utc)

# En deca de cet ecart, on ne touche a rien : `mvhd` ne porte pas de fuseau,
# et un decalage de quelques heures peut n'etre qu'une lecture locale/UTC.
MARGE_H = 6

# Cloudinary RE-ENCODE certaines videos et rehorodate `mvhd` avec l'heure du
# traitement. On reconnait sa signature : la date du fichier tombe alors sur
# l'heure d'ENVOI, a la minute pres. Mesure sur les 13 candidats : 4 etaient
# dans ce cas (3 de Gal, 1 de Malen, ecart 0 a 1 min), et les « corriger »
# aurait remplace une date juste par l'heure d'upload.
# Rejeter est toujours sans risque : quand quelqu'un filme et envoie dans la
# foulee, la date declaree est deja bonne, donc ne rien faire est correct.
MARGE_TRANSCODE_MIN = 90

AIDE_CLE = """\
Cle de service absente ou inutilisable : {key}

Mise en place, une fois :
  1. https://console.cloud.google.com -> projet `africatrip-eea1a`.
  2. IAM et administration -> Comptes de service -> en creer un.
  3. Lui donner le role « Utilisateur Cloud Datastore ».
  4. Cles -> Ajouter une cle -> JSON, puis telecharger.
  5. Enregistrer sous .firestore-credentials.json a la racine du depot.
     Le fichier est deja git-ignore : il ne partira jamais sur GitHub."""


def jeton():
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            key = json.load(f)
        key["client_email"], key["private_key"]  # noqa: B018 — valide la forme
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        raise SystemExit(AIDE_CLE.format(key=os.path.normpath(KEY_FILE)))
    from google.auth import crypt, jwt as gjwt
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    assertion = gjwt.encode(
        crypt.RSASigner.from_service_account_info(key),
        {"iss": key["client_email"], "scope": SCOPE, "aud": TOKEN_URL,
         "iat": now, "exp": now + 3600},
    ).decode()
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion}).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body), timeout=30) as r:
        return json.load(r)["access_token"]


def date_du_fichier(url):
    """Date de creation lue dans l'atome `mvhd` du conteneur, ou None.

    On ne telecharge que les deux extremites : `moov` est en tete quand le
    fichier est prepare pour le streaming, en queue sinon.
    """
    for plage in ("0-524287", "-524288"):
        try:
            req = urllib.request.Request(url)
            req.add_header("Range", f"bytes={plage}")
            bloc = urllib.request.urlopen(req, timeout=60).read()
        except Exception:
            continue
        i = bloc.find(b"mvhd")
        if i < 0:
            continue
        try:
            version = bloc[i + 4]
            brut = (struct.unpack(">Q", bloc[i + 8:i + 16])[0] if version == 1
                    else struct.unpack(">I", bloc[i + 8:i + 12])[0])
        except (struct.error, IndexError):
            continue
        # Bornes de plausibilite : ~1999 a ~2037 depuis le 1er janvier 1904.
        if 3e9 < brut < 4.2e9:
            return EPOCH_MP4 + datetime.timedelta(seconds=brut)
    return None


def lire_instant(v):
    """Un champ date Firestore -> datetime UTC, ou None."""
    if not v:
        return None
    try:
        s = str(v)[:19]
        if len(s) == 10:
            s += "T00:00:00"
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S") \
            .replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def lire_declare(f):
    for cle in ("capturedAt", "at", "date"):
        v = f.get(cle)
        if not v:
            continue
        try:
            s = str(v)[:19]
            if len(s) == 10:
                s += "T00:00:00"
            return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S") \
                .replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


def ecrire(token, project, doc_id, quand):
    """Patch cible : uniquement `capturedAt` et `date`."""
    url = (f"https://firestore.googleapis.com/v1/projects/{project}/databases/"
           f"(default)/documents/photos/{doc_id}"
           "?updateMask.fieldPaths=capturedAt&updateMask.fieldPaths=date")
    corps = json.dumps({"fields": {
        "capturedAt": {"timestampValue": quand.strftime("%Y-%m-%dT%H:%M:%SZ")},
        "date": {"stringValue": quand.strftime("%Y-%m-%d")}}}).encode()
    req = urllib.request.Request(url, data=corps, method="PATCH",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--commit", action="store_true", help="ecrire (sinon simple apercu)")
    args = ap.parse_args()

    project, key = firebase_config()
    videos = []
    for doc in fs_list(project, key, "photos"):
        f = fields(doc)
        url = str(f.get("url") or "")
        if f.get("type") == "video" or "/video/upload/" in url:
            videos.append((doc["name"].rsplit("/", 1)[-1], f))
    print(f"{len(videos)} videos a examiner\n")

    corrections, illisibles, deja_bon, transcodees = [], 0, 0, 0
    for doc_id, f in videos:
        vraie = date_du_fichier(f.get("url"))
        if vraie is None:
            illisibles += 1
            continue
        declaree = lire_declare(f)
        ecart_h = abs((vraie - declaree).total_seconds()) / 3600 if declaree else 1e9
        if ecart_h <= MARGE_H:
            deja_bon += 1
            continue
        # Signature du transcodage : on ne touche pas.
        envoi = lire_instant(f.get("at"))
        if envoi and abs((vraie - envoi).total_seconds()) / 60 <= MARGE_TRANSCODE_MIN:
            transcodees += 1
            continue
        corrections.append((doc_id, f.get("displayName") or f.get("name"),
                            declaree, vraie, ecart_h))

    corrections.sort(key=lambda c: -c[4])
    print(f"  {deja_bon} deja correctes (ecart <= {MARGE_H} h), "
          f"{illisibles} sans date lisible dans le fichier,")
    print(f"  {transcodees} ecartees : date du fichier = heure d'envoi "
          f"(rehorodatees par Cloudinary)")
    print(f"  {len(corrections)} a corriger :\n")
    for _, qui, declaree, vraie, ecart in corrections:
        d = declaree.strftime("%d/%m %H:%M") if declaree else "aucune"
        print(f"    {qui:8}  declaree {d}  ->  reelle {vraie.strftime('%d/%m %H:%M')}"
              f"   ({ecart:.0f} h d'ecart)")

    if not args.commit:
        print("\n[APERCU] Rien ecrit. Relancer avec --commit pour appliquer.")
        return
    if not corrections:
        print("\nRien a faire.")
        return

    token = jeton()
    faits = 0
    for doc_id, qui, _, vraie, _ in corrections:
        try:
            ecrire(token, project, doc_id, vraie)
            faits += 1
        except urllib.error.HTTPError as e:
            print(f"  echec sur {qui} ({doc_id}) : {e.code} {e.reason}")
    print(f"\n{faits}/{len(corrections)} videos redatees.")
    print("Le site les reprendra au prochain instantane horaire "
          "(ou lancer : python src/fetch_tracks.py && python src/build.py).")


if __name__ == "__main__":
    main()
