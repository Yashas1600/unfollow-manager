#!/usr/bin/env python3
"""
Instagram Auto-Unfollow Bot
Scrapes followers/following lists and identifies who doesn't follow you back.

WARNING: This violates Instagram's ToS. Use at your own risk.
"""

import os
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# --- Configuration ---
IG_USERNAME = ""  # set your username here
SCROLL_PAUSE_SECONDS = 3  # wait for new profiles to load after each scroll


def get_usernames_from_modal(page):
    """Scroll through a followers/following modal and collect all usernames."""
    usernames = set()
    stale_rounds = 0
    max_stale_rounds = 2  # wait for more to load twice before giving up

    time.sleep(3)

    def collect_usernames():
        return page.evaluate("""
            () => {
                const dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return [];
                const links = dialog.querySelectorAll('a[href^="/"]');
                const names = [];
                const skip = new Set([
                    'explore', 'reels', 'direct', 'accounts', 'p',
                    'stories', 'tags', 'locations', 'about', 'privacy',
                ]);
                for (const a of links) {
                    const parts = a.getAttribute('href').split('/').filter(Boolean);
                    if (parts.length === 1 && !skip.has(parts[0])) {
                        names.push(parts[0]);
                    }
                }
                return names;
            }
        """)

    def do_scroll():
        """Scroll all scrollable divs inside the dialog to the bottom."""
        page.evaluate("""
            () => {
                const dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return;
                const divs = dialog.querySelectorAll('div');
                for (const d of divs) {
                    if (d.scrollHeight > d.clientHeight + 10) {
                        d.scrollTop = d.scrollHeight;
                    }
                }
            }
        """)

    while stale_rounds < max_stale_rounds:
        prev_count = len(usernames)

        found = collect_usernames()
        usernames.update(found)

        new_count = len(usernames)
        if new_count > prev_count:
            stale_rounds = 0
            print(f"  Loaded {new_count} usernames so far...")
        else:
            stale_rounds += 1
            # When no new names appear, wait a bit longer to let Instagram load
            if stale_rounds <= 5:
                print(f"  Waiting for more to load... (attempt {stale_rounds}/{max_stale_rounds})")
                time.sleep(2)  # extra wait on top of the normal scroll pause

        do_scroll()
        time.sleep(SCROLL_PAUSE_SECONDS)

    return usernames


def scrape_list(page, profile_url, list_type):
    """Navigate to profile, click followers/following, and scrape the modal."""
    print(f"\nScraping {list_type} list...")

    page.goto(profile_url)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(4)

    # Click on the followers/following link
    clicked = False
    for selector in [
        f'a[href*="/{list_type}"]',
        f'a[href$="/{list_type}/"]',
    ]:
        try:
            link = page.locator(selector).first
            if link.is_visible():
                link.click()
                clicked = True
                print(f"  Clicked: {selector}")
                break
        except Exception:
            continue

    if not clicked:
        try:
            page.locator("a", has_text=list_type).first.click()
            clicked = True
            print(f"  Clicked via text: {list_type}")
        except Exception:
            pass

    if not clicked:
        print(f"  ERROR: Could not click {list_type} link!")
        page.screenshot(path=f"debug_{list_type}_fail.png")
        return set()

    time.sleep(4)

    # Wait for modal
    try:
        page.locator('[role="dialog"]').first.wait_for(timeout=10000)
        print(f"  Modal opened")
    except PlaywrightTimeout:
        print(f"  WARNING: Modal not detected, trying to scrape anyway...")

    page.screenshot(path=f"debug_{list_type}.png")

    usernames = get_usernames_from_modal(page)
    print(f"  Total {list_type}: {len(usernames)}")

    # Close modal
    page.keyboard.press("Escape")
    time.sleep(2)

    return usernames


def main():
    print("=" * 50)
    print("Instagram Non-Followers Finder")
    print("=" * 50)
    print()

    profile_url = f"https://www.instagram.com/{IG_USERNAME}/"
    print(f"Profile: @{IG_USERNAME}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        page.goto("https://www.instagram.com/accounts/login/")
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        print("\n>>> Browser opened. Log into Instagram.")
        print(">>> Once you see your feed, come back here and press ENTER.")
        input(">>> Press ENTER to continue...\n")

        # Go to profile
        print("Navigating to your profile...")
        page.goto(profile_url)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        # Scrape both lists
        followers = scrape_list(page, profile_url, "followers")
        following = scrape_list(page, profile_url, "following")

        # Compute non-followers
        non_followers = following - followers

        print(f"\n{'=' * 50}")
        print(f"Followers:      {len(followers)}")
        print(f"Following:      {len(following)}")
        print(f"Non-followers:  {len(non_followers)}")
        print(f"{'=' * 50}")

        if not non_followers:
            print("\nEveryone you follow follows you back!")
        else:
            # Save lists
            with open("followers.txt", "w") as f:
                for u in sorted(followers):
                    f.write(u + "\n")

            with open("following.txt", "w") as f:
                for u in sorted(following):
                    f.write(u + "\n")

            with open("non_followers.txt", "w") as f:
                for u in sorted(non_followers):
                    f.write(u + "\n")

            print(f"\nAccounts that DON'T follow you back:")
            print("-" * 40)
            for i, u in enumerate(sorted(non_followers), 1):
                print(f"  {i:3}. @{u}")
            print("-" * 40)

            print(f"\nSaved to:")
            print(f"  followers.txt     ({len(followers)} accounts)")
            print(f"  following.txt     ({len(following)} accounts)")
            print(f"  non_followers.txt ({len(non_followers)} accounts)")

        browser.close()


if __name__ == "__main__":
    main()
