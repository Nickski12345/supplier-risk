# Supplier risk: weekly negative-news scan

Every Monday at 07:00 UTC a Claude Code cloud routine scans the news for each
supplier in `suppliers.csv`. It writes only High and Critical items to the
"Supplier Risk – Weekly Negative News" Claude Doc. Vulnerabilities and CVE news
are excluded, because existing feeds already cover them.

## How it works

The Claude Doc has three tabs:

- **Dashboard**: this week's High and Critical items, rewritten every run.
- **Risk register**: one row per finding. New rows arrive with Status "New";
  people fill in Owner, Status and Actions. The run never edits or deletes rows.
- **Suppliers**: the list that gets scanned. Add a row to monitor a new supplier.

Each Monday the routine (see `ROUTINE.md`):

1. Reads the Suppliers tab, and `import_suppliers.py` turns it into
   `suppliers.csv`. If the tab can't be read, the run stops without changing the doc.
2. `collect_news.py` pulls 7 days of candidate articles per supplier from Google
   News RSS and GDELT into `data/raw.json`.
3. Reads the Risk register, so events already tracked aren't added twice.
4. Claude classifies the candidates and writes `data/findings.json`.
5. `validate_findings.py` rejects any finding that doesn't cite a collected article.
6. `build_dashboard.py` renders the dashboard sections, the chart and the new
   register rows into `out/`, and Claude writes them into the doc.

`doc_ids.json` holds the doc, tab, chart and dropdown IDs.

## Supplier columns

| Column | Required | Meaning |
| --- | --- | --- |
| Supplier | yes | Name as it appears in the news |
| Aliases | no | Other names, separated by `;` |
| Size | no | Large, Medium or Small (for reference) |
| Country | no | For reference |
| Exclude terms | no | Words that mark a namesake, separated by `;` |

The supplier list is never committed: this repo is public, so `suppliers.csv` is
generated at run time from the Suppliers tab and is git-ignored.

## Running it locally

```
python collect_news.py --no-gdelt   # needs internet; --no-gdelt skips the slower source
```

Uses only the Python 3.10+ standard library.
