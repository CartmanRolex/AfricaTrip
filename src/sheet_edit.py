"""
Read and WRITE the live trip Google Sheet from the command line.

Usage:
    python src/sheet_edit.py tabs                         # list tabs (name + gid)
    python src/sheet_edit.py get  "A1:E5"                 # print a range
    python src/sheet_edit.py set  "B3" "new value"        # write one cell
    python src/sheet_edit.py set  "B3:D3" v1 v2 v3        # write one row
    python src/sheet_edit.py setrows "A10:C12" rows.json  # write a 2-D block
    python src/sheet_edit.py clear "Z100"                 # clear a range

Ranges use A1 notation and may be prefixed with a tab name ("Feuille 1!B3");
without a prefix the first tab is used. `setrows` takes a JSON file (or an
inline JSON string) holding a list of rows, e.g. [["a","b"],["c","d"]].

Auth is a Google Cloud service account. One-time setup:
  1. In Google Cloud console, create a project and enable the Google Sheets API.
  2. Create a service account (no roles needed) and download a JSON key.
  3. Save the key as `.sheet-credentials.json` in the repo root (git-ignored).
  4. Share the sheet with the service account's email as Editor.

The sheet itself is identified via the local, git-ignored `.sheet-url` file
(same as refresh.py). Only google-auth is needed beyond the standard library;
the Sheets API v4 calls themselves use plain urllib.
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request

from refresh import configured_sheet, sheet_id

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(HERE, "..", ".sheet-credentials.json")
SCOPE = "https://www.googleapis.com/auth/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://sheets.googleapis.com/v4/spreadsheets"

SETUP_HELP = """\
Missing or unusable service account key: {key}

One-time setup:
  1. https://console.cloud.google.com -> create/pick a project.
  2. Enable the "Google Sheets API" for it.
  3. IAM & Admin -> Service Accounts -> create one (no roles), then
     Keys -> Add key -> JSON, and download it.
  4. Save it as .sheet-credentials.json in the repo root (it is git-ignored).
  5. Share the trip sheet with the service account email as Editor."""


def load_key():
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            key = json.load(f)
        key["client_email"], key["private_key"]  # noqa: B018 — validate shape
        return key
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        raise RuntimeError(SETUP_HELP.format(key=os.path.normpath(KEY_FILE)))


def access_token(key):
    """Exchange a signed service-account JWT for a bearer token (no transport deps)."""
    from google.auth import crypt, jwt as gjwt
    now = int(time.time())
    assertion = gjwt.encode(
        crypt.RSASigner.from_service_account_info(key),
        {"iss": key["client_email"], "scope": SCOPE, "aud": TOKEN_URL,
         "iat": now, "exp": now + 3600},
    ).decode()
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=body)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["access_token"]


def api_call(token, method, path, payload=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e)["error"]["message"]
        except Exception:
            msg = e.reason
        hint = ""
        if e.code == 403:
            email = load_key()["client_email"]
            hint = f"\nIs the sheet shared with {email} as Editor?"
        raise RuntimeError(f"Sheets API {e.code}: {msg}{hint}")


def quoted(a1_range):
    return urllib.parse.quote(a1_range, safe="")


def parse_rows(arg):
    """`setrows` data: a path to a JSON file, or an inline JSON list of rows."""
    if os.path.exists(arg):
        with open(arg, encoding="utf-8") as f:
            rows = json.load(f)
    else:
        rows = json.loads(arg)
    if not (isinstance(rows, list) and all(isinstance(r, list) for r in rows)):
        raise ValueError("Expected a JSON list of rows, e.g. [[\"a\",\"b\"],[\"c\"]]")
    return rows


def print_values(result):
    for row in result.get("values", []):
        print("\t".join(str(c) for c in row))


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("tabs", "get", "set", "setrows", "clear"):
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    cmd, rest = args[0], args[1:]
    if cmd != "tabs" and not rest:
        raise ValueError(f"'{cmd}' needs an A1 range, e.g. \"B3\" or \"Feuille 1!A1:C5\"")

    sheet = configured_sheet()
    if not sheet:
        raise RuntimeError("No .sheet-url file found — same setup as refresh.py.")
    sid = sheet_id(sheet)
    token = access_token(load_key())

    if cmd == "tabs":
        meta = api_call(token, "GET", f"/{sid}?fields=sheets.properties")
        for s in meta["sheets"]:
            p = s["properties"]
            print(f"{p['title']}\t(gid={p['sheetId']})")
    elif cmd == "get":
        print_values(api_call(token, "GET", f"/{sid}/values/{quoted(rest[0])}"))
    elif cmd in ("set", "setrows"):
        if len(rest) < 2:
            raise ValueError(f"'{cmd}' needs a range and value(s).")
        rows = parse_rows(rest[1]) if cmd == "setrows" else [rest[1:]]
        result = api_call(
            token, "PUT",
            f"/{sid}/values/{quoted(rest[0])}?valueInputOption=USER_ENTERED",
            {"values": rows})
        print(f"Updated {result.get('updatedCells', 0)} cell(s) in "
              f"{result.get('updatedRange', rest[0])}")
    elif cmd == "clear":
        result = api_call(token, "POST", f"/{sid}/values/{quoted(rest[0])}:clear")
        print(f"Cleared {result.get('clearedRange', rest[0])}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, urllib.error.URLError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
