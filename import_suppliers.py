"""Turn the doc's Suppliers table (exported to data/suppliers_doc.json) into suppliers.csv.

Input: a JSON list of {"name", "aliases", "size", "country", "exclude_terms"},
one object per table row, copied cell-for-cell from the Suppliers tab.
Cells are typed by people, so every value is cleaned and length-capped.
If the input is missing, empty or invalid, suppliers.csv is left untouched
(the copy in the repo is the fallback) and the script exits 1.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "data" / "suppliers_doc.json"
DEST = ROOT / "suppliers.csv"
MAX_SUPPLIERS = 200  # keeps a run within news-source rate limits and usage
MAX_LEN = 100
FIELDS = ["name", "aliases", "country", "size", "exclude_terms"]


def clean(v) -> str:
    v = re.sub(r"[\x00-\x1f\x7f\"<>]", " ", str(v or ""))
    return re.sub(r"\s+", " ", v).strip()[:MAX_LEN]


def clean_list(v) -> str:
    return ";".join(p for p in (clean(x) for x in str(v or "").split(";")) if p)


def main() -> int:
    try:
        rows = json.loads(SRC.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Cannot read {SRC.name}: {e}. Keeping the repo's suppliers.csv.", file=sys.stderr)
        return 1
    if not isinstance(rows, list):
        print("suppliers_doc.json must be a list. Keeping the repo's suppliers.csv.", file=sys.stderr)
        return 1

    out, seen = [], set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = clean(r.get("name"))
        if len(name) < 2 or name.lower() in seen or name.lower() == "supplier":
            continue
        seen.add(name.lower())
        out.append({"name": name, "aliases": clean_list(r.get("aliases")),
                    "country": clean(r.get("country"))[:40], "size": clean(r.get("size"))[:20],
                    "exclude_terms": clean_list(r.get("exclude_terms"))})
    if not out:
        print("No supplier rows found. Keeping the repo's suppliers.csv.", file=sys.stderr)
        return 1
    if len(out) > MAX_SUPPLIERS:
        print(f"{len(out)} suppliers; only the first {MAX_SUPPLIERS} will be scanned.", file=sys.stderr)
        out = out[:MAX_SUPPLIERS]

    with DEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    print(f"Wrote {len(out)} suppliers from the doc to {DEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
