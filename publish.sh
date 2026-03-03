#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Renaming files and fetching page titles ==="
python3 rename.py

echo ""
echo "=== Building data.json ==="
python3 build.py

echo ""
echo "=== Publishing to GitHub ==="
git add .
git commit -m "update mailings $(date +%Y-%m-%d)" || echo "(nothing new to commit)"
git push

echo ""
echo "Done. Site will update in ~1 minute at https://bobmarteal.github.io/lyris/"
