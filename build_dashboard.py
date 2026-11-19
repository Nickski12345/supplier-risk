"""Turn validated findings into the exact content written to the Claude Doc.

Writes to out/:
  glance.md        one paragraph for "This week at a glance"
  critical.md      table (or one sentence) for "Critical"
  high.md          table (or one sentence) for "High"
  chart_module.js  widget module for the "flagged suppliers" chart

Article-derived text is escaped here, so a headline cannot inject markdown,
links or doc chip tokens into the dashboard.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import urllib.parse
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw.json"
FINDINGS = ROOT / "data" / "findings.json"
OUT = ROOT / "out"
CHART_MAX_SUPPLIERS = 15


def esc(text: str) -> str:
    text = re.sub(r"[\x00-\x1f<>]", " ", str(text))  # no raw HTML or <?claude ...?> tokens
    text = text.replace("\\", "\\\\")
    for ch in "|[]*_`#~":
        text = text.replace(ch, "\\" + ch)
    return re.sub(r"\s+", " ", text).strip()


def safe_url(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return ""
    return urllib.parse.quote(url, safe=":/?#&=%+@,;~!$*'-._")  # encodes ( ) < > spaces


def nice(d: str) -> str:
    return dt.date.fromisoformat(d).strftime("%d %b %Y").lstrip("0")


def table(rows: list[dict]) -> str:
    if not rows:
        return ""
    lines = ["| Supplier | What happened | Category | Date | Source |",
             "| --- | --- | --- | --- | --- |"]
    for f in rows:
        url = safe_url(f["url"])
        src = f"[{esc(f['source_name'])}]({url})" if url else esc(f["source_name"])
        what = f"**{esc(f['headline'])}**. {esc(f['summary'])}"
        lines.append(f"| {esc(f['supplier'])} | {what} | {esc(f['category'])} | {nice(f['date'])} | {src} |")
    return "\n".join(lines)


def ref_for(f: dict) -> str:
    return "R-" + hashlib.sha1(f"{f['supplier']}|{f['url']}".encode()).hexdigest()[:6].upper()


def cell(*inline) -> dict:
    return {"type": "cell", "content": [{"type": "paragraph", **({"content": list(inline)} if inline else {})}]}


def txt(t: str, href: str | None = None) -> dict:
    node = {"type": "text", "text": re.sub(r"[\x00-\x1f]", " ", str(t)).strip() or "-"}
    if href:
        node["marks"] = [{"type": "link", "attrs": {"href": href}}]
    return node


def register_rows(items: list[dict], enums: dict, existing: set[str]) -> list[dict]:
    """Table rows (Docs block JSON) for findings that are not in the register yet."""
    rows = []
    for f in sorted(items, key=lambda f: (f["severity"] != "Critical", f["supplier"])):
        ref = ref_for(f)
        if f.get("existing_ref") or ref in existing:
            continue
        url = safe_url(f["url"])
        rows.append({"type": "row", "content": [
            cell(txt(ref)),
            cell(txt(f["supplier"])),
            cell({"type": "dropdown", "enum": enums["severity"], "index": 0 if f["severity"] == "Critical" else 1}),
            cell(txt(f["category"])),
            cell(txt(f"{f['headline']}. {f['summary']}")),
            cell(txt(nice(f["date"]))),
            cell(txt(f["source_name"], url or None)),
            cell({"type": "dropdown", "enum": enums["status"], "index": 0}),
            cell(),
            cell(),
        ]})
    return rows


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "supplier"


def chart_module(items: list[dict]) -> str:
    counts: dict[str, dict] = {}
    for f in items:
        c = counts.setdefault(f["supplier"], {"supplier": f["supplier"], "slug": slug(f["supplier"]),
                                              "critical": 0, "high": 0})
        c["critical" if f["severity"] == "Critical" else "high"] += 1
    rows = sorted(counts.values(), key=lambda r: (-r["critical"], -(r["critical"] + r["high"]), r["supplier"]))
    rows = rows[:CHART_MAX_SUPPLIERS]
    data = json.dumps(rows, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e")
    return (
        "export default () => <claude.Visualize data-claude-component='flagged-suppliers' "
        "sources={{rows:{kind:'data', data:" + data + "}}}>{({rows, datum}) => { "
        "const n = rows.length, maxT = Math.max(1, ...rows.map(r => r.critical + r.high)); "
        "const crit = rows.reduce((s, r) => s + r.critical, 0), high = rows.reduce((s, r) => s + r.high, 0); "
        "const left = 230, y0 = 96, rowH = 30, w = 470, sx = v => v / maxT * w, H = y0 + Math.max(n, 1) * rowH + 24; "
        "return <svg viewBox={`0 0 760 ${H}`} role='img' aria-label='Suppliers with High or Critical news in the last 7 days' fontSize='12'>"
        "<text data-claude-text-id='title' x='20' y='30' fontSize='16' fill='var(--cds-text-primary)'>Suppliers with High or Critical news in the last 7 days</text>"
        "<text x='20' y='52' fill='var(--cds-text-secondary)'>{n === 0 ? 'No suppliers flagged' : `${crit} Critical and ${high} High items across ${n} suppliers`}</text>"
        "<g data-claude-anchor='legend'><rect x='20' y='66' width='12' height='12' fill='var(--cds-chart-status-critical)' fillOpacity='0.85'/>"
        "<text data-claude-text-id='legend-critical' x='38' y='76' fill='var(--cds-text-secondary)'>Critical</text>"
        "<rect x='100' y='66' width='12' height='12' fill='var(--cds-chart-status-serious)' fillOpacity='0.55'/>"
        "<text data-claude-text-id='legend-high' x='118' y='76' fill='var(--cds-text-secondary)'>High</text></g>"
        "<g data-claude-anchor='bars'>{rows.map((r, i) => <g key={r.slug} data-claude-anchor={`supplier-${r.slug}`}>"
        "<text x={left - 10} y={y0 + i * rowH + 18} textAnchor='end' fill='var(--cds-text-primary)'>{r.supplier.length > 32 ? r.supplier.slice(0, 31) + '…' : r.supplier}</text>"
        "<rect x={left} y={y0 + i * rowH + 5} width={sx(r.critical)} height='18' fill='var(--cds-chart-status-critical)' fillOpacity='0.85' {...datum(r, 'critical')}><title>{`${r.supplier}: ${r.critical} Critical`}</title></rect>"
        "<rect x={left + sx(r.critical)} y={y0 + i * rowH + 5} width={sx(r.high)} height='18' fill='var(--cds-chart-status-serious)' fillOpacity='0.55' {...datum(r, 'high')}><title>{`${r.supplier}: ${r.high} High`}</title></rect>"
        "<text x={left + sx(r.critical + r.high) + 8} y={y0 + i * rowH + 18} fill='var(--cds-text-secondary)' {...datum(r)}>{r.critical + r.high}</text>"
        "</g>)}</g>"
        "{n === 0 ? <text data-claude-text-id='empty' x='20' y={y0 + 18} fill='var(--cds-text-secondary)'>No High or Critical items this week.</text> : null}"
        "</svg>; }}</claude.Visualize>;"
    )


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    items = json.loads(FINDINGS.read_text(encoding="utf-8"))["items"]
    order = lambda f: (f["date"], f["supplier"])
    crit = sorted((f for f in items if f["severity"] == "Critical"), key=order, reverse=True)
    high = sorted((f for f in items if f["severity"] == "High"), key=order, reverse=True)
    n_sup = len(raw["suppliers"])
    window = f"{nice(raw['window_start'])} to {nice(raw['window_end'])}"

    if items:
        top = Counter(f["supplier"] for f in items).most_common(3)
        flagged = len({f["supplier"] for f in items})
        glance = (f"**{len(crit)} Critical** and **{len(high)} High** items across {flagged} of {n_sup} "
                  f"suppliers, {window}. Most affected: "
                  + ", ".join(f"{esc(s)} ({c})" for s, c in top) + ".")
    else:
        glance = f"No High or Critical items for any of the {n_sup} suppliers, {window}."
    failed = {e["supplier"] for e in raw.get("errors", []) if e["feed"] == "google_news"}
    if failed:
        glance += f" News feeds failed for {len(failed)} supplier(s), so coverage is incomplete this week."

    OUT.mkdir(exist_ok=True)
    (OUT / "glance.md").write_text(glance, encoding="utf-8")
    (OUT / "critical.md").write_text(table(crit) or "No Critical items this week.", encoding="utf-8")
    (OUT / "high.md").write_text(table(high) or "No High items this week.", encoding="utf-8")
    (OUT / "chart_module.js").write_text(chart_module(items), encoding="utf-8")
    enums = json.loads((ROOT / "doc_ids.json").read_text(encoding="utf-8"))["enums"]
    reg_file = ROOT / "data" / "register_refs.json"
    existing = set(json.loads(reg_file.read_text(encoding="utf-8"))) if reg_file.exists() else set()
    new_rows = register_rows(items, enums, existing)
    (OUT / "register_rows.json").write_text(json.dumps(new_rows, ensure_ascii=False), encoding="utf-8")
    print(f"Risk register: {len(new_rows)} new rows")
    print(f"Built dashboard content: {len(crit)} Critical, {len(high)} High -> {OUT}")


if __name__ == "__main__":
    main()
