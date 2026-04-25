# Unfollow Manager

Find and remove Instagram accounts that don't follow you back.

## Quick Start (Development)

```bash
pip install flask playwright
playwright install chromium
python3 app.py
```

Open http://127.0.0.1:8080

## How It Works

1. **Login** — Opens a browser window. Log into Instagram manually.
2. **Scan** — Automatically detects your account and fetches followers/following via Instagram's API.
3. **Review** — Shows everyone who doesn't follow you back. Uncheck anyone you want to keep.
4. **Unfollow** — Removes selected accounts with rate limiting to avoid blocks.

## Build Desktop App

Requires Node.js and Python 3.

```bash
# Build everything
./build.sh
```

Or step by step:

```bash
# 1. Bundle Python backend
pip install pyinstaller
pyinstaller --onefile --name app \
  --add-data "templates:templates" \
  --add-data "static:static" \
  --distpath backend_dist \
  app.py

# 2. Build Electron app
cd electron
npm install
npm run build
```

The built app will be in `dist/`.

## Run in Electron (Dev Mode)

```bash
cd electron
npm install
npm start
```

## Disclaimer

This tool uses browser automation and Instagram's internal APIs. It may violate Instagram's Terms of Service. Use at your own risk.
