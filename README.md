# Unfollow Manager

Find and remove Instagram accounts that don't follow you back.

## Features

- Scans your followers and following lists via Instagram's internal API
- Shows who doesn't follow you back
- Review the list and uncheck anyone you want to keep (influencers, brands, friends)
- Unfollow selected accounts automatically with rate limiting
- Dark, minimal UI

## Getting Started

### Desktop App (Recommended)

Download the latest release from the [Releases](https://github.com/Yashas1600/unfollow-manager/releases) page.

Or build it yourself:

```bash
# 1. Bundle the Python backend
pip install pyinstaller flask playwright
pyinstaller --onefile --name app \
  --add-data "templates:templates" \
  --add-data "static:static" \
  --distpath backend_dist \
  app.py

# 2. Build the Electron app
cd electron
npm install
npm run build
```

The built `.dmg` (Mac) or `.exe` (Windows) will be in `dist/`.

### Run from Source

```bash
# Install dependencies
pip install flask playwright
playwright install chromium

# Start the app
python3 app.py
```

Then open `http://127.0.0.1:8080` in your browser.

### Run with Electron (Dev Mode)

```bash
cd electron
npm install
npm start
```

## How It Works

1. **Login** — A browser window opens. Log into Instagram manually. Your credentials are never stored.
2. **Scan** — The app detects your account and fetches your followers/following lists via Instagram's API.
3. **Review** — See everyone who doesn't follow you back. Uncheck anyone you want to keep.
4. **Unfollow** — Removes selected accounts with delays between each to avoid rate limiting.

## Disclaimer

This tool uses browser automation and Instagram's internal APIs, which may violate Instagram's Terms of Service. Use at your own risk. The authors are not responsible for any account restrictions or bans.
