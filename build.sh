#!/bin/bash
# Build the Unfollow Manager desktop app
set -e

echo "=== Building Python backend ==="
pip install pyinstaller playwright flask
pyinstaller --onefile --name app \
  --add-data "templates:templates" \
  --add-data "static:static" \
  --hidden-import playwright \
  --distpath backend_dist \
  app.py

echo ""
echo "=== Installing Electron dependencies ==="
cd electron
npm install

echo ""
echo "=== Building desktop app ==="
npm run build

echo ""
echo "=== Done! Check the dist/ folder ==="
