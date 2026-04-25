from playwright.sync_api import sync_playwright
import time

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False)
page = browser.new_page()
page.goto("https://www.instagram.com/accounts/login/")
input("Log in, then press ENTER...")

page.goto("https://www.instagram.com/ojszzzn/")
time.sleep(4)

btn = page.locator("button").filter(has_text="Following").first
print(f"Found Following button: {btn.is_visible()}")
btn.click()
time.sleep(2)

clicked = page.evaluate("""() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
        if (walker.currentNode.textContent.trim() === 'Unfollow') {
            walker.currentNode.parentElement.click();
            return true;
        }
    }
    return false;
}""")
print(f"Clicked Unfollow: {clicked}")
time.sleep(3)
input("Check result, press ENTER to close...")
browser.close()
pw.stop()
