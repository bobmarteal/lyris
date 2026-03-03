# A&S Newsletter Analytics

A lightweight static website for browsing and filtering Lyris bulk email analytics reports for the Cornell College of Arts & Sciences.

## What it does

The College sends newsletters to several mailing lists — Faculty, Staff, Students, and Graduate Students — using Lyris, an older bulk email platform. Lyris can export per-campaign analytics as XML files, but the raw exports are hard to read and impossible to compare across campaigns.

This site solves that by:

- Parsing all the XML exports into a single structured dataset
- Displaying each campaign as a card with key stats (sent, open rate, click rate, unsubscribes)
- Showing a ranked table of clicked links for each campaign, with fetched page titles
- Letting you filter by list, year, and semester — instantly, with no page reload
- Hosting everything as a static site on GitHub Pages — no server, no login, no dependencies

## How to add a new mailing

1. Download the analytics export from Lyris and save it anywhere in this folder (the raw `.html` or `.xml.html` file — exact filename doesn't matter)
2. Run:
   ```
   ./prepare.sh
   ```
   This will:
   - Rename the file to the standard `type-YYYY-MM-DD.xml` format
   - Archive the original to `temporary/`
   - Fetch the page title for each clicked URL and write it back into the XML
   - Rebuild `data.json`
   - Start a local preview at [http://localhost:8000](http://localhost:8000)
3. Review the site locally, then push:
   ```
   git add .
   git commit -m "add faculty 2026-03-01"
   git push
   ```
   GitHub Pages updates automatically within a minute.

## File structure

```
analytics/
├── index.html          # The site — single file, inline CSS + JS, no dependencies
├── data.json           # Generated dataset consumed by the site
├── build.py            # Parses all XML files and writes data.json
├── rename.py           # Renames raw exports, fetches page titles
├── prepare.sh          # Runs rename.py + build.py + local preview server
├── temporary/          # Archived originals (gitignored)
└── *.xml               # One file per campaign
```

## File naming convention

Each XML file is named `{type}-{YYYY-MM-DD}.xml`, where `type` is derived from the `<list>` field in the XML — stripping the `as-` prefix and `-update-l` suffix:

```
as-faculty-update-l  →  faculty-2026-01-20.xml
as-graduatestudents-update-l  →  graduatestudents-2026-02-05.xml
```

## Notes

- The site filters are built dynamically from the data — new list types or years appear automatically
- If you accidentally drop in a duplicate file, `rename.py` will detect it and leave everything unchanged, printing a clear warning
- Some clicked URLs are behind paywalls or redirects; those show "Not Available" as the page title
- Lyris mislabels click counts as `<opens>` in its XML — this is accounted for in `build.py`
