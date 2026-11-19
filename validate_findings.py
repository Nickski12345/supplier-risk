"""Check data/findings.json before anything reaches the dashboard.

Guardrail: every finding must cite articles that exist in data/raw.json,
so a hallucinated or injected item (made-up URL, unknown supplier,
out-of-range severity) is rejected rather than published.
Exit 0 = valid, 1 = errors listed on stderr.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw.json"
FINDINGS = ROOT / "data" / "findings.json"

SEVERITIES = {"Critical", "High"}
CATEGORIES = {
    "Workforce reduction", "Legal / regulatory", "Financial distress",
    "Change of control", "Leadership change", "Operational disruption",
    "Cyber incident", "Sanctions / ESG",
}
LIMITS = {"headline": 160, "summary": 400, "source_name": 120}


def main() -> int:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    findings = json.loads(FINDINGS.read_text(encoding="utf-8"))
    by_id = {it["id"]: it for it in raw["items"]}
    suppliers = set(raw["suppliers"])
    start = dt.date.fromisoformat(raw["window_start"]) - dt.timedelta(days=1)
    end = dt.date.fromisoformat(raw["window_end"]) + dt.timedelta(days=1)
    errs: list[str] = []

    items = findings.get("items")
    if not isinstance(items, list):
        print("findings.json: 'items' must be a list", file=sys.stderr)
        return 1
    seen = set()
    for n, f in enumerate(items):
        where = f"items[{n}]"
        if not isinstance(f, dict):
            errs.append(f"{where}: not an object")
            continue
        if f.get("supplier") not in suppliers:
            errs.append(f"{where}: supplier {f.get('supplier')!r} is not in suppliers.csv")
        if f.get("severity") not in SEVERITIES:
            errs.append(f"{where}: severity must be one of {sorted(SEVERITIES)}")
        if f.get("category") not in CATEGORIES:
            errs.append(f"{where}: category must be one of {sorted(CATEGORIES)}")
        for key, lim in LIMITS.items():
            v = f.get(key)
            if not isinstance(v, str) or not v.strip() or len(v) > lim:
                errs.append(f"{where}: {key} must be a non-empty string of at most {lim} chars")
        ids = f.get("item_ids")
        if not isinstance(ids, list) or not ids:
            errs.append(f"{where}: item_ids must list the raw.json ids it is based on")
            continue
        missing = [i for i in ids if i not in by_id]
        if missing:
            errs.append(f"{where}: item_ids not found in raw.json: {missing}")
            continue
        if f.get("url") not in {by_id[i]["url"] for i in ids}:
            errs.append(f"{where}: url must be the url of one of its item_ids")
        if any(by_id[i]["supplier"] != f.get("supplier") for i in ids):
            errs.append(f"{where}: item_ids were collected for a different supplier")
        try:
            d = dt.date.fromisoformat(f.get("date", ""))
            if not start <= d <= end:
                errs.append(f"{where}: date {d} is outside the 7-day window")
        except (TypeError, ValueError):
            errs.append(f"{where}: date must be YYYY-MM-DD")
        ref = f.get("existing_ref")
        if ref is not None and not (isinstance(ref, str) and re.fullmatch(r"R-[0-9A-F]{6}", ref)):
            errs.append(f"{where}: existing_ref must look like R-1A2B3C or be omitted")
        key = (f.get("supplier"), f.get("url"))
        if key in seen:
            errs.append(f"{where}: duplicate of an earlier finding (same supplier and url)")
        seen.add(key)

    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    print(f"OK: {len(items)} findings valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
