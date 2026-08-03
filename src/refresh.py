"""
One-shot IMPORT from the live Google Sheet — no longer part of the build.

The Google Sheet is NOT the reference any more: the trip data lives in the repo
(`data/*.csv` + `src/site-overrides.json`) and is edited there. This script is
kept only to re-import from a sheet on purpose, and it OVERWRITES `data/*.csv`,
so it refuses to run without an explicit flag.

Usage:
    python src/refresh.py --from-sheet                    # sheet in .sheet-url
    python src/refresh.py --from-sheet <sheet-url-or-id>  # a different sheet
    python src/refresh.py --from-sheet <url> --gid 123456 # a specific tab

To rebuild the site from the repo data — the normal case — run instead:
    python src/parse_csv.py && python src/build.py

It downloads the sheet as CSV into data/, then runs the full pipeline
(parse_csv -> build) so voyage-afrique.html reflects the imported sheet.

The sheet link is NOT stored in this repo. Keep it in a local, git-ignored
file at the repo root called `.sheet-url` (one line: the sheet URL or ID), or
pass it on the command line. That way the link never ends up on GitHub.

The sheet must be shared as "anyone with the link can view" for the CSV
export to work without authentication. Only the Python standard library is
required.
"""
import argparse, os, re, runpy, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_OUT = os.path.join(HERE, "..", "data", "AfriqueCalendrier_-_Presences_Voyage.csv")
SHEET_FILE = os.path.join(HERE, "..", ".sheet-url")

# The "Config" tab (route, RPG stats, textes…) — created 2026-07, stable gid.
CONFIG_GID = "2029368965"
CONFIG_OUT = os.path.join(HERE, "..", "data", "Config.csv")


def configured_sheet():
    """Read the sheet URL/ID from the local, git-ignored .sheet-url file."""
    try:
        with open(SHEET_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except FileNotFoundError:
        pass
    return None


def sheet_id(url_or_id):
    """Accept a full Google Sheets URL or a bare ID and return the ID."""
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", url_or_id.strip()):
        return url_or_id.strip()
    raise ValueError(f"Could not find a Google Sheet ID in: {url_or_id!r}")


def gid_from(url_or_id):
    """Pull a tab gid out of a URL (…#gid=123 or …&gid=123), else None."""
    m = re.search(r"[#&?]gid=(\d+)", url_or_id)
    return m.group(1) if m else None


def export_url(url_or_id, gid=None):
    sid = sheet_id(url_or_id)
    gid = gid or gid_from(url_or_id)
    url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv"
    if gid:
        url += f"&gid={gid}"
    return url


def download_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read().decode("utf-8")
    # A non-public sheet redirects to an HTML sign-in page instead of CSV.
    if data.lstrip().lower().startswith("<!doctype html") or "<html" in data[:200].lower():
        raise RuntimeError(
            "The sheet did not return CSV — it is probably not shared publicly. "
            "Set sharing to 'anyone with the link can view' and try again.")
    return data


def main():
    ap = argparse.ArgumentParser(
        description="Import the trip data from a Google Sheet (overwrites data/*.csv).")
    ap.add_argument("sheet", nargs="?", default=None,
                    help="Google Sheets URL or ID (default: read from .sheet-url)")
    ap.add_argument("--gid", help="specific tab gid (optional)")
    ap.add_argument("--from-sheet", action="store_true",
                    help="required: confirm you really want to overwrite data/*.csv")
    args = ap.parse_args()

    if not args.from_sheet:
        ap.error(
            "the Google Sheet is no longer the reference — the trip data lives in "
            "data/*.csv and src/site-overrides.json.\n"
            "  To rebuild the site:   python src/parse_csv.py && python src/build.py\n"
            "  To really re-import and OVERWRITE data/*.csv:  add --from-sheet")

    sheet = args.sheet or configured_sheet()
    if not sheet:
        ap.error(
            f"No sheet specified. Pass a URL/ID on the command line, or create "
            f"{os.path.normpath(SHEET_FILE)} with the sheet URL on one line. "
            "That file is git-ignored so the link stays local, not on GitHub.")

    url = export_url(sheet, args.gid)
    print(f"Downloading {url}")
    csv_text = download_csv(url)

    os.makedirs(os.path.dirname(CSV_OUT), exist_ok=True)
    with open(CSV_OUT, "w", encoding="utf-8", newline="") as f:
        f.write(csv_text)
    print(f"Saved {os.path.normpath(CSV_OUT)} ({len(csv_text):,} bytes)")

    # The Config tab is optional: keep the last local copy if it can't be fetched.
    try:
        cfg_text = download_csv(export_url(sheet, CONFIG_GID))
        with open(CONFIG_OUT, "w", encoding="utf-8", newline="") as f:
            f.write(cfg_text)
        print(f"Saved {os.path.normpath(CONFIG_OUT)} ({len(cfg_text):,} bytes)")
    except Exception as e:
        print(f"WARNING: could not fetch the Config tab ({e}) — "
              "using the existing local data/Config.csv if present.")

    # Run the existing pipeline in-process so paths resolve the same way.
    runpy.run_path(os.path.join(HERE, "parse_csv.py"), run_name="__main__")
    runpy.run_path(os.path.join(HERE, "build.py"), run_name="__main__")
    print("Done — open voyage-afrique.html")


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, RuntimeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
