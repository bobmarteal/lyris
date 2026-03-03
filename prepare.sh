#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Renaming files and fetching page titles ==="
python3 rename.py

echo ""
echo "=== Building data.json ==="
python3 build.py

echo ""
echo "=== Starting local preview at http://localhost:8000 ==="
echo "When you're happy, open a new terminal tab and run:"
echo "  git add . && git commit -m 'add mailings' && git push"
echo ""
echo "Press Ctrl+C to stop the server."
echo ""

# Kill anything already on 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

python3 -m http.server 8000
