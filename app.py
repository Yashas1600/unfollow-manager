#!/usr/bin/env python3
"""
Instagram Unfollow Manager — Web App
Flask backend with Playwright browser automation.
All Playwright operations run on a single dedicated thread.
"""

import json
import os
import random
import time
import threading
import queue
from flask import Flask, render_template, request, jsonify
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

app = Flask(__name__)

# ── Single Playwright worker thread ────────────────────────────────────
# All browser operations go through this queue to avoid thread issues.

work_queue = queue.Queue()
result_store = {}
result_events = {}

# Shared state for UI polling
app_state = {
    "browser_open": False,
    "logged_in": False,
    "scan_status": "idle",  # idle, scanning, done, error
    "scan_message": "",
    "followers": [],
    "following": [],
    "non_followers": [],
    "unfollow_active": False,
    "unfollow_total": 0,
    "unfollow_completed": 0,
    "unfollow_statuses": {},  # username -> status
}


def get_user_id(page, username):
    """Extract Instagram user ID from a profile page."""
    page.goto(f"https://www.instagram.com/{username}/")
    page.wait_for_load_state("domcontentloaded")
    time.sleep(1.5)

    # Try multiple methods to extract user ID
    user_id = page.evaluate("""
        () => {
            // Method 1: from page source / shared data
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                const text = s.textContent || '';
                // Look for profilePage pattern
                const match = text.match(/"profilePage_([0-9]+)"/);
                if (match) return match[1];
                // Look for user_id pattern
                const match2 = text.match(/"user_id":"([0-9]+)"/);
                if (match2) return match2[1];
                const match3 = text.match(/"id":"([0-9]+)"/);
                if (match3 && text.includes('"username"')) return match3[1];
            }
            // Method 2: from meta tags or links
            const meta = document.querySelector('meta[property="al:ios:url"]');
            if (meta) {
                const match = meta.content.match(/user\\?id=([0-9]+)/);
                if (match) return match[1];
            }
            return null;
        }
    """)

    if not user_id:
        # Method 3: use the web profile info API
        user_id = page.evaluate("""
            async (username) => {
                try {
                    const res = await fetch(`/api/v1/users/web_profile_info/?username=${username}`, {
                        headers: { 'x-ig-app-id': '936619743392459' }
                    });
                    const data = await res.json();
                    return data?.data?.user?.id || null;
                } catch (e) {
                    return null;
                }
            }
        """, username)

    return user_id


def get_profile_counts(page, username):
    """Get the real follower/following counts from the profile page."""
    return page.evaluate("""
        (username) => {
            const counts = {};
            const links = document.querySelectorAll('a[href*="/' + username + '/"]');
            for (const a of links) {
                const href = a.getAttribute('href') || '';
                const text = a.textContent || '';
                const numMatch = text.replace(/,/g, '').match(/([0-9]+)/);
                if (numMatch) {
                    if (href.includes('followers')) counts.followers = parseInt(numMatch[1]);
                    else if (href.includes('following')) counts.following = parseInt(numMatch[1]);
                }
            }
            return counts;
        }
    """, username)


def fetch_list_via_api(page, user_id, list_type, expected_count):
    """Fetch followers or following list via Instagram's internal API."""
    app_state["scan_message"] = f"Fetching {list_type} (expecting ~{expected_count})..."
    usernames = set()
    max_id = ""
    empty_retries = 0
    max_pages = 200  # safety limit

    for _ in range(max_pages):
        url_suffix = f"&max_id={max_id}" if max_id else ""
        result = page.evaluate("""
            async ([userId, listType, urlSuffix]) => {
                try {
                    const res = await fetch(
                        `/api/v1/friendships/${userId}/${listType}/?count=200${urlSuffix}`,
                        { headers: { 'x-ig-app-id': '936619743392459' } }
                    );
                    const data = await res.json();
                    const users = (data.users || []).map(u => u.username);
                    return {
                        users: users,
                        next_max_id: data.next_max_id || null,
                        status: data.status
                    };
                } catch (e) {
                    return { users: [], next_max_id: null, error: e.toString() };
                }
            }
        """, [user_id, list_type, url_suffix])

        if result.get("error"):
            app_state["scan_message"] = f"API error: {result['error']}"
            break

        new_users = result.get("users", [])
        prev_count = len(usernames)
        usernames.update(new_users)
        app_state["scan_message"] = f"Found {len(usernames)}/{expected_count} {list_type}..."

        next_max_id = result.get("next_max_id")

        if len(usernames) == prev_count:
            empty_retries += 1
            if empty_retries >= 5:
                break
            time.sleep(2)
            continue
        else:
            empty_retries = 0

        # Got all of them
        if expected_count and len(usernames) >= expected_count:
            break

        if not next_max_id:
            # API says no more but we're missing people — retry
            if expected_count and len(usernames) < expected_count * 0.99:
                empty_retries += 1
                if empty_retries >= 5:
                    break
                time.sleep(2)
                continue
            break

        max_id = next_max_id

    return usernames


def scrape_list(page, profile_url, list_type, user_id, expected_count):
    """Fetch followers or following using the API."""
    app_state["scan_message"] = f"Fetching {list_type}..."
    return fetch_list_via_api(page, user_id, list_type, expected_count or 0)


def unfollow_user(page, username):
    page.goto(f"https://www.instagram.com/{username}/")
    page.wait_for_load_state("domcontentloaded")
    time.sleep(1.5)

    # Click the "Following" button — try fast first, retry if not found
    def find_following_btn():
        for selector in [
            'button:has-text("Following")',
            'button:has-text("Requested")',
            '[aria-label="Following"]',
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible():
                    return btn
            except Exception:
                continue
        return None

    following_btn = find_following_btn()
    if not following_btn:
        time.sleep(2.5)
        following_btn = find_following_btn()
    if not following_btn:
        return "skip"

    following_btn.click()
    time.sleep(2)

    # Click "Unfollow" — try twice for possible confirmation dialog
    def click_unfollow():
        return page.evaluate("""
            () => {
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT
                );
                while (walker.nextNode()) {
                    if (walker.currentNode.textContent.trim() === 'Unfollow') {
                        walker.currentNode.parentElement.click();
                        return true;
                    }
                }
                return false;
            }
        """)

    if not click_unfollow():
        page.keyboard.press("Escape")
        return "skip"

    time.sleep(0.5)
    click_unfollow()  # second confirmation if it exists
    time.sleep(0.5)
    page.keyboard.press("Escape")
    return "success"


def playwright_worker():
    """Single thread that owns the Playwright browser and processes all commands."""
    pw = sync_playwright().start()
    browser = None
    page = None

    while True:
        try:
            cmd = work_queue.get(timeout=1)
        except queue.Empty:
            continue

        action = cmd.get("action")
        task_id = cmd.get("id")

        try:
            if action == "open_browser":
                browser = pw.chromium.launch(headless=False)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                page = context.new_page()
                page.goto("https://www.instagram.com/accounts/login/")
                page.wait_for_load_state("domcontentloaded")
                app_state["browser_open"] = True
                set_result(task_id, {"status": "ok"})

            elif action == "check_login":
                # Check if user has navigated away from login page
                url = page.url if page else ""
                logged_in = (
                    page is not None
                    and "login" not in url
                    and "challenge" not in url
                    and "instagram.com" in url
                )
                if logged_in:
                    app_state["logged_in"] = True
                set_result(task_id, {"logged_in": logged_in})

            elif action == "scan":
                app_state["scan_status"] = "scanning"
                app_state["scan_message"] = "Detecting your username..."

                # Auto-detect username from logged-in session
                page.goto("https://www.instagram.com/")
                page.wait_for_load_state("domcontentloaded")
                time.sleep(3)

                # Find the profile link in the nav/sidebar
                username = page.evaluate("""
                    () => {
                        // Look for profile link in nav
                        const links = document.querySelectorAll('a[href^="/"]');
                        for (const a of links) {
                            const text = (a.textContent || '').toLowerCase();
                            const ariaLabel = (a.getAttribute('aria-label') || '').toLowerCase();
                            if (text.includes('profile') || ariaLabel.includes('profile')) {
                                const parts = a.getAttribute('href').split('/').filter(Boolean);
                                if (parts.length === 1) return parts[0];
                            }
                        }
                        return null;
                    }
                """)

                if not username:
                    # Fallback: go to accounts/edit to find username
                    page.goto("https://www.instagram.com/accounts/edit/")
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(3)
                    username = page.evaluate("""
                        () => {
                            const input = document.querySelector('input[name="username"]');
                            if (input) return input.value;
                            // Try to get from URL or page content
                            const spans = document.querySelectorAll('span');
                            for (const s of spans) {
                                if (s.textContent && s.textContent.match(/^[a-zA-Z0-9._]+$/)) {
                                    return s.textContent;
                                }
                            }
                            return null;
                        }
                    """)

                if not username:
                    app_state["scan_status"] = "error"
                    app_state["scan_message"] = "Could not detect username. Please try again."
                    set_result(task_id, {"status": "error"})
                    continue

                app_state["scan_message"] = f"Found @{username}, getting user ID..."
                app_state["username"] = username
                profile_url = f"https://www.instagram.com/{username}/"

                user_id = get_user_id(page, username)
                if not user_id:
                    app_state["scan_status"] = "error"
                    app_state["scan_message"] = "Could not get user ID. Try again."
                    set_result(task_id, {"status": "error"})
                    continue

                # Get real counts from profile page
                page.goto(profile_url)
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)
                real_counts = get_profile_counts(page, username)

                app_state["scan_message"] = f"Got user ID, fetching followers..."
                followers = scrape_list(page, profile_url, "followers", user_id, real_counts.get("followers"))
                following = scrape_list(page, profile_url, "following", user_id, real_counts.get("following"))
                non_followers = following - followers

                app_state["followers"] = sorted(followers)
                app_state["following"] = sorted(following)
                app_state["non_followers"] = sorted(non_followers)
                app_state["profile_follower_count"] = real_counts.get("followers", len(followers))
                app_state["profile_following_count"] = real_counts.get("following", len(following))
                app_state["scan_status"] = "done"
                app_state["scan_message"] = "Scan complete"
                set_result(task_id, {"status": "done"})

            elif action == "unfollow":
                usernames = cmd["usernames"]
                app_state["unfollow_active"] = True
                app_state["unfollow_total"] = len(usernames)
                app_state["unfollow_completed"] = 0

                for i, username in enumerate(usernames):
                    try:
                        status = unfollow_user(page, username)
                    except Exception as e:
                        status = "error"

                    app_state["unfollow_statuses"][username] = status
                    app_state["unfollow_completed"] = i + 1

                    if i < len(usernames) - 1:
                        delay = random.uniform(2, 4)
                        time.sleep(delay)

                app_state["unfollow_active"] = False
                set_result(task_id, {"status": "done"})

            elif action == "shutdown":
                if browser:
                    browser.close()
                pw.stop()
                break

        except Exception as e:
            app_state["scan_status"] = "error"
            app_state["scan_message"] = str(e)
            set_result(task_id, {"status": "error", "message": str(e)})


def set_result(task_id, result):
    if task_id:
        result_store[task_id] = result
        if task_id in result_events:
            result_events[task_id].set()


def send_command(action, **kwargs):
    """Send a command to the Playwright worker and optionally wait for result."""
    task_id = f"{action}_{time.time()}"
    evt = threading.Event()
    result_events[task_id] = evt
    work_queue.put({"action": action, "id": task_id, **kwargs})
    return task_id, evt


# ── Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start-login", methods=["POST"])
def start_login():
    if app_state["browser_open"]:
        return jsonify({"status": "already_open"})
    task_id, evt = send_command("open_browser")
    evt.wait(timeout=30)
    return jsonify(result_store.get(task_id, {"status": "timeout"}))


@app.route("/login-status")
def login_status():
    """Poll to check if user has logged in."""
    if app_state["logged_in"]:
        return jsonify({"logged_in": True})
    if not app_state["browser_open"]:
        return jsonify({"logged_in": False})
    task_id, evt = send_command("check_login")
    evt.wait(timeout=5)
    result = result_store.get(task_id, {"logged_in": False})
    return jsonify(result)


@app.route("/scan", methods=["POST"])
def scan():
    if not app_state["browser_open"]:
        return jsonify({"error": "Browser not open"}), 400

    send_command("scan")
    return jsonify({"status": "scanning"})


@app.route("/scan-status")
def scan_status():
    return jsonify({
        "status": app_state["scan_status"],
        "message": app_state["scan_message"],
        "followers": app_state["followers"],
        "following": app_state["following"],
        "non_followers": app_state["non_followers"],
        "profile_follower_count": app_state.get("profile_follower_count"),
        "profile_following_count": app_state.get("profile_following_count"),
    })


@app.route("/unfollow", methods=["POST"])
def unfollow():
    data = request.get_json()
    usernames = data.get("usernames", [])
    if not usernames:
        return jsonify({"error": "No usernames"}), 400

    app_state["unfollow_statuses"] = {}
    send_command("unfollow", usernames=usernames)
    return jsonify({"status": "started", "total": len(usernames)})


@app.route("/unfollow-status")
def unfollow_status():
    return jsonify({
        "active": app_state["unfollow_active"],
        "total": app_state["unfollow_total"],
        "completed": app_state["unfollow_completed"],
        "statuses": app_state["unfollow_statuses"],
    })


# ── Main ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Start Playwright worker thread
    worker = threading.Thread(target=playwright_worker, daemon=True)
    worker.start()

    print("=" * 50)
    print("Instagram Unfollow Manager")
    print("Open http://127.0.0.1:8080 in your browser")
    print("=" * 50)
    port = int(os.environ.get("FLASK_PORT", 8080))
    app.run(debug=False, port=port, host="127.0.0.1")
