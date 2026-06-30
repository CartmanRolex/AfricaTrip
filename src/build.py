"""
Build the final standalone site by injecting src/data.json into src/template.html.

Usage:  python src/build.py
Reads:  src/template.html  (contains the literal token __DATA__)
        src/data.json
Writes: voyage-afrique.html  (self-contained, open directly in a browser)

Full pipeline to rebuild from the raw CSV:
    python src/parse_csv.py   # CSV  -> src/data.json
    python src/build.py       # JSON -> voyage-afrique.html
"""
import os

HERE = os.path.dirname(__file__)
TEMPLATE = os.path.join(HERE, "template.html")
DATA = os.path.join(HERE, "data.json")
OUT = os.path.join(HERE, "..", "voyage-afrique.html")

def main():
    template = open(TEMPLATE, encoding="utf-8").read()
    data = open(DATA, encoding="utf-8").read()
    html = template.replace("__DATA__", data)
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"Wrote {os.path.normpath(OUT)} ({len(html):,} chars)")

if __name__ == "__main__":
    main()
