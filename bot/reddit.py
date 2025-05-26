import requests
import random
import time
import json
import hashlib
import uuid
import os
from datetime import datetime

import functools
import os
import time

print = functools.partial(print, flush=True)

PAUSE_FLAG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pause.flag"))

def wait_if_paused():
    was_paused = False
    while os.path.exists(PAUSE_FLAG):
        if not was_paused:
            print("⏸️ Bot paused...")  # tylko raz
            was_paused = True
        time.sleep(1)
    if was_paused:
        print("▶️ Bot resumed.")


def pause_point():
    if os.path.exists(PAUSE_FLAG):
        print("⏸️ I'm pausing before this action...")
        wait_if_paused()


from playwright.sync_api import sync_playwright
from .config import CONFIG, REDDIT_TO_ADSPOWER, BLOCKED_KEYWORDS, BLOCKED_SUBREDDITS
from .helpers import get_device_id


class RedditAutomation:
    def __init__(self):
        self.api_url = "https://api-3vgi.onrender.com"
        self.sheet_name = CONFIG["google_sheet"]
        self.sheet_data = self.fetch_sheet_data()
        self.last_used_user_id = None

        self.email = CONFIG["email"]
        self.password = CONFIG["password"]
        self.num_accounts = CONFIG.get("num_accounts", 1)

    def fetch_sheet_data(self):
        for attempt in range(3):
            try:
                response = requests.get(
                    f"{self.api_url}/get-sheet",
                    params={"sheet": self.sheet_name},
                    timeout=30
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"❌ Error fetching sheet data: {response.status_code}")
            except Exception as e:
                print(f"❌ attempt {attempt+1}: Exception while fetching the sheet: {e}")
                time.sleep(5)
        return []

    def check_remote_auth_via_api(self, email, password, num_accounts):
        try:
            pause_point()
            response = requests.post(
                f"{self.api_url}/check_auth",
                json={
                    "email": email,
                    "password": password,
                    "num_accounts": num_accounts,
                    "device_id": get_device_id(),
                },
                timeout=30
            )
            data = response.json()
            # Ignorujemy dodatkowe dane, żeby nie wywalało błędu
            optional_keys = ["google_sheet", "api_key", "adspower_api_url", "deepseek_api_key", "REDDIT_TO_ADSPOWER"]
            for key in optional_keys:
                data.pop(key, None)

            return data.get("status") == "ok"
        except Exception as e:
            print(f"❌ API authorization error: {e}")
            return False
        
    def get_reddit_name_for_user(self, user_id):
        for reddit, adspower in REDDIT_TO_ADSPOWER.items():
            if adspower == user_id:
                return reddit
        return "❓ nieznane_konto"
    
    def get_random_unused_post(self, user_id):
        records = self.sheet_data

        # Mapowanie user_id → nazwa konta Reddit
        reddit_name = None
        for reddit, adspower in REDDIT_TO_ADSPOWER.items():
            if adspower == user_id:
                reddit_name = reddit
                break

        if not reddit_name:
            print(f"❌ ❌ Reddit account name not found for user_id '{user_id}'")
            return None

        # Filtrujemy nieużyte posty przypisane do tego konta
        unused_posts = [
            post for post in records
            if not post.get("Użyty", "").strip() and post.get("Konto", "").strip().lower() == reddit_name.lower()
        ]

        return random.choice(unused_posts) if unused_posts else None

    def mark_post_as_used(self, title):
        try:
            pause_point()
            response = requests.post(
                f"{self.api_url}/mark_post_used",
                json={
                    "sheet_name": self.sheet_name,
                    "title": title,
                    "used_posts_column": CONFIG["used_posts_column"]
                },
                timeout=10
            )
            data = response.json()
            if data.get("status") == "ok":
                print("✅ Marked post as used")
            elif data.get("status") == "not_found":
                print("⚠️ No post found to mark.")
            else:
                print(f"❌ Server error: {data.get('message')}")
        except Exception as e:
            print(f"❌ Error connecting to API when marking post as used:{e}")

    def start_adspower_profile(self, user_id):
        params = {"user_id": user_id, "api_key": CONFIG["api_key"]}
        response = requests.get(CONFIG["adspower_api_url"], params=params).json()

        if response["code"] != 0:
            raise Exception(f"Błąd API: {response.get('msg', 'Nieznany błąd')}")

        ws_data = response["data"].get("ws", {})
        debugger_url = (
            ws_data.get("cdp") or
            ws_data.get("puppeteer") or
            f"ws://127.0.0.1:{response['data'].get('debug_port')}/devtools/browser/{user_id}"
        )

        if not debugger_url:
            raise Exception("Cannot find the debug URL in the API response.")

        print(f"Debug URL: {debugger_url}")
        return debugger_url
    def stop_adspower_profile(self, user_id):
        """
        Zamyka profil AdsPower dla danego user_id.
        """
        url = f"http://local.adspower.net:50325/api/v1/browser/stop"
        params = {
            "user_id": user_id,
            "api_key": CONFIG["api_key"]
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                print(f"🛑 AdsPower profile closed: {user_id}")
            else:
                print(f"⚠️ Failed to close profile {user_id}, status: {response.status_code}")
        except Exception as e:
            print(f"❌ Error while closing AdsPower profile: {e}")

    def simulate_file_upload_in_shadow_dom(self, page, file_path, shadow_host_selector):
        """
        Symuluje upload pliku do inputa ukrytego w Shadow DOM.
        """
        file_input_selector = f"{shadow_host_selector} >>> input.file-input"
        file_input_handle = page.query_selector(file_input_selector)
        if not file_input_handle:
            raise Exception(f"Input not found using: {file_input_selector}")
        pause_point()
        file_input_handle.set_input_files(file_path)

    def generate_comment_from_title(self, title):
        """
        Generuje komentarz na podstawie tytułu posta, korzystając z API DeepSeek.
        """
        import requests

        API_KEY = CONFIG.get("deepseek_api_key")
        API_URL = "https://api.deepseek.com/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }

        prompt_template = CONFIG.get(
            "comment_prompt_template",
            'You\'re replying to a Reddit post titled: "{title}". Write a short, friendly comment.'
        )
        prompt = prompt_template.format(title=title)

        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a helpful Reddit commenter."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.8
        }

        try:
            pause_point()
            response = requests.post(API_URL, headers=headers, json=data, timeout=15)
            result = response.json()
            print("🧠 AI answer:", result)
            return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print("❌ Error generating comment:", e)
            return None

    def maybe_scroll_main_page(self, page):
        """
        Losowo skroluje stronę główną Reddita, by symulować naturalne zachowanie.
        """
        if random.random() < CONFIG.get("scroll_homepage_probability", 0.5):
            print("🎲 Drawn: BOT is scrolling the main page (in multiple phases)...")
            num_phases = random.randint(3, 9)
            print(f"🌀 Scrolling in {num_phases} phases...")

            for phase in range(num_phases):
                pause_point()
                steps = random.randint(20, 50)
                step_size = random.randint(10, 25)
                delay = random.uniform(0.01, 0.05)

                print(f"  🪄 Phase {phase+1}: {steps} steps x {step_size}px (delay {delay:.3f}s)")

                for _ in range(steps):
                    page.evaluate(f"window.scrollBy(0, {step_size});")
                    time.sleep(delay)

                pause = random.uniform(0.5, 1.5)
                print(f"  ⏸️ Pause {pause:.2f}s before the next phase")
                time.sleep(pause)

            print("✅ Scrolling completed.")
        else:
            print("🎲 Drawn: BOT skips main page scrolling.")

    def maybe_comment_on_random_post(self, page):
        pause_point()
        """
        Losowo próbuje dodać komentarz pod cudzym postem na stronie głównej Reddita.
        """
        try:
            should_comment = random.random() < CONFIG.get("comment_probability", 0.34)
            if not should_comment:
                print("🎲 Drawn: skipping comment.")
                return False

            print("💬 Drawn: trying to add a comment under someone else's post...")

            posts = page.query_selector_all("article")
            if not posts:
                print("❌ No posts found on the page.")
                return False

            visible_posts = posts[:5] if len(posts) >= 5 else posts
            random_post = None

            for post in visible_posts:
                title_el = post.query_selector("a[id^='post-title-']")
                if not title_el:
                    continue

                title = title_el.inner_text().strip()
                if not title:
                    continue

                title_lower = title.lower()
                if any(keyword in title_lower for keyword in BLOCKED_KEYWORDS):
                    print("🚫 Title contains a word from the blocklist – skipping post.")
                    continue

                post_link_el = post.query_selector("a[href*='/comments/']")
                if post_link_el:
                    post_url = post_link_el.get_attribute("href")
                    import re
                    match = re.search(r"/r/([^/]+)/", post_url)
                    if match:
                        subreddit_name = match.group(1).lower()
                        if subreddit_name in BLOCKED_SUBREDDITS:
                            print(f"🚫 Subreddit r/{subreddit_name} is blocked – skipping.")
                            continue

                # ✅ Jeśli przeszliśmy wszystkie filtry – użyjemy tego posta
                random_post = post
                break

            if not random_post:
                print("❌ No post passed the filters – skipping commenting.")
                return False

            title_el = random_post.query_selector("a[id^='post-title-']")
            if not title_el:
                print("❌ Title not found.")
                return False

            title = title_el.inner_text().strip()
            if not title:
                print("⚠️ Empty title.")
                return False

            title_lower = title.lower()
            print(f"📝 Selected post title: {title}")

            if any(keyword in title_lower for keyword in BLOCKED_KEYWORDS):
                print("🚫 Title contains a word from the blocklist – skipping post.")
                return False

            comment = self.generate_comment_from_title(title)
            if not comment:
                print("⚠️ Failed to generate comment.")
                return False

            import unicodedata

            # 🧼 Czyścimy cudzysłowy i znaki sterujące
            comment = comment.strip()
            while comment and comment[0] in "\"'""''":
                comment = comment[1:]
            while comment and comment[-1] in "\"'""''":
                comment = comment[:-1]
            comment = ''.join(c for c in comment if unicodedata.category(c)[0] != "C")

            print(f"💬 Comment: {comment}")

            post_link_el = random_post.query_selector("a[href*='/comments/']")
            if post_link_el:
                post_url = post_link_el.get_attribute("href")
                print(f"📎 Going to the post: {post_url}")

                # 🧠 Wyciągamy nazwę subreddita z URL
                import re
                match = re.search(r"/r/([^/]+)/", post_url)
                if match:
                    subreddit_name = match.group(1).lower()
                    if subreddit_name in BLOCKED_SUBREDDITS:
                        print(f"🚫 Subreddit r/{subreddit_name} is on the blocklist – skipping.")
                        return False

                # ⏱️ Czekamy dłużej przed przejściem (naturalne opóźnienie)
                delay = random.uniform(3, 7)
                print(f"💤 Waiting {delay:.2f} seconds before navigating to the post...")
                time.sleep(delay)

                page.goto(f"https://www.reddit.com{post_url}", timeout=60000)
                time.sleep(3)

            try:
                print("🖱️ Searching for and clicking the 'Comment' button, if it exists...")
                comment_btn = page.locator("button[name='comments-action-button']")
                if comment_btn and comment_btn.is_visible():
                    comment_btn.click()
                    time.sleep(2)

                print("⏳ Searching for the component...")
                composer = page.locator("shreddit-composer")
                try:
                    composer.wait_for(state="visible", timeout=10000)
                    print("✅ component is visible.")
                except Exception:
                    print("❌ component is NOT visible.")
                    return False

                # Szukamy input_box w kilku wariantach selektorów
                possible_inputs = [
                    "div[contenteditable='true'][role='textbox']",
                    "div[slot='rte'][contenteditable='true']",
                    "div[slot='editor'][contenteditable='true']",
                ]

                input_box = None
                for selector in possible_inputs:
                    if not selector.strip():
                        continue
                    print(f"🔍 Testing selector: 1")
                    try:
                        box = composer.locator(selector)
                        if box.count() > 0:
                            input_box = box.first
                            print(f"✅ Found input_box using selector: 1")
                            break
                    except Exception as e:
                        print(f"❌ Error with selector 1: {e}")

                if not input_box:
                    print("❌ No text field found using known selectors.")
                    return False
                try:
                    input_box.wait_for(state="visible", timeout=10000)
                    print("✅ text field is visible.")
                except Exception:
                    print("❌ text field not found.")
                    return

                try:
                    input_box.click(force=True)
                    print("✅ Clicked on the text field.")
                    page.wait_for_timeout(500)
                except Exception as e:
                    print(f"❌ Error clicking text field: {e}")
                    return

                try:
                    input_box.type(comment, delay=50)
                    print(f"✅ Comment entered: {comment}")

                    page.locator("body").click()
                    print("🧠 Clicked on the body to lose focus.")

                    pause = random.uniform(6, 12)
                    print(f"💤 Waiting {pause:.2f} seconds after entering the comment...")
                    pause_point()
                    time.sleep(pause)
                except Exception as e:
                    print(f"❌ Error entering the comment: {e}")
                    return

                print("🔍 Searching for the button to publish the comment...")

                possible_submit_selectors = [
                    "shreddit-composer >>> button:has-text('Comment')",
                    "shreddit-composer >>> button[type='submit']",
                    "shreddit-composer >>> faceplate-button >> text=Comment"
                ]

                submit_btn = None
                for selector in possible_submit_selectors:
                    try:
                        btn = page.locator(selector)
                        if btn.count() > 0 and btn.first.is_visible():
                            submit_btn = btn.first
                            print(f"✅ Found the button to publish the comment: 1")
                            break
                    except Exception as e:
                        print(f"❌ Error searching for the submit button: 1")

                if not submit_btn:
                    print("❌ No button found to publish the comment.")
                    return False

                try:
                    submit_btn.click()
                    pause = random.uniform(6, 16)
                    print(f"💤 Waiting {pause:.2f} seconds after clicking the publish button...")
                    time.sleep(pause)
                    print("✅ Clicked the publish button – the comment should be published.")
                except Exception as e:
                    print(f"❌ Error clicking the publish button: 1")
                    return

                print("🎉 Comment added successfully!")
                return True

            except Exception as outer:
                print(f"💥 Unexpected exception: {outer}")
                return False

        except Exception as e:
            print(f"❌ Error adding the comment: {e}")
            return False

    def post_to_reddit(self, user_id, post_data):
        """
        Publikuje post na Reddita na wybranym koncie, obsługuje upload, flair, tekst, link, obrazek.
        """
        from playwright.sync_api import sync_playwright
        browser = None
        try:
            with sync_playwright() as p:
                debugger_url = self.start_adspower_profile(user_id)
                browser = p.chromium.connect_over_cdp(debugger_url)
                context = browser.contexts[0]
                page = context.new_page()

                print("🌐 Opening the main Reddit page...")
                pause_point()
                page.goto("https://www.reddit.com", timeout=60000)

                pause = random.uniform(2, 9)
                print(f"🌐 Waiting {pause:.2f}s for the page to load...")
                time.sleep(pause)

                self.maybe_scroll_main_page(page)

                comment_added = self.maybe_comment_on_random_post(page)

                if comment_added:
                    pause_range = CONFIG.get("pause_after_comment", [100, 210])
                    pause_after_comment = random.uniform(*pause_range)
                    print(f"⏱️ Pause after comment: {pause_after_comment // 60:.0f} min")
                    pause_point()
                    time.sleep(pause_after_comment)

                print(f"📍 Going to r/{post_data['Subreddit']}...")
                pause_point()
                page.goto(f"https://www.reddit.com/r/{post_data['Subreddit']}", timeout=60000)
                time.sleep(3)

                try:
                    print("📝 Clicking 'Create Post'...")
                    page.wait_for_selector("a[href$='/submit']", timeout=10000)
                    page.click("a[href$='/submit']")
                    pause_point()
                    time.sleep(3)
                except Exception:
                    raise Exception("❌ Failed to click the 'Create Post' button")

                if post_data.get("Flair"):
                    try:
                        print("⏳ Waiting for the 'Add flair' button...")
                        page.wait_for_selector("button#reddit-post-flair-button", timeout=15000)

                        print("🔍 Searching for the 'Add flair' button...")
                        flair_button = page.locator("button#reddit-post-flair-button")

                        if flair_button.count() > 0 and flair_button.first.is_visible():
                            print("🖱️ Clicking the flair button with force=True...")
                            flair_button.first.click(force=True)

                            print("⏳ Waiting for the flair popup...")
                            page.locator("div[role='dialog']:not([hidden])").first.wait_for(state="visible", timeout=10000)

                            try:
                                all_buttons = page.locator("span:has-text('View all flairs')")
                                count = all_buttons.count()

                                if count == 0:
                                    print("ℹ️ No 'View all flairs' button found.")
                                else:
                                    clicked = False
                                    for i in range(count):
                                        btn = all_buttons.nth(i)
                                        try:
                                            if btn.is_visible():
                                                btn.click()
                                                print(f"✅ Clicked the 'View all flairs' button (element #1).")
                                                clicked = True
                                                break
                                        except Exception as e:
                                            print(f"⚠️ Failed to click the button #1")

                                    if not clicked:
                                        print("⚠️ None of the 'View all flairs' buttons were clickable.")

                            except Exception as e:
                                print(f"❌ Error searching for 'View all flairs': 1")

                            flairs = page.locator("faceplate-radio-input").all()
                            if not flairs:
                                print("⚠️ No available flairs found.")
                            else:
                                desired_flair = post_data.get("Flair", "").strip().lower()
                                chosen = None

                                for flair in flairs:
                                    try:
                                        flair_text = flair.get_attribute("data-text")
                                        if not flair_text:
                                            try:
                                                flair_text = flair.locator("div.rendererd-rtjson").first.inner_text(timeout=1000)
                                            except:
                                                pass
                                        if not flair_text:
                                            try:
                                                flair_text = flair.inner_text(timeout=1000)
                                            except:
                                                pass
                                        if not flair_text:
                                            continue
                                        flair_text = flair_text.strip().lower()
                                        if flair_text == desired_flair:
                                            flair.click()
                                            chosen = flair_text
                                            print(f"✅ Selected flair: {flair_text}")
                                            break
                                    except Exception as e:
                                        print(f"⚠️ Failed to get the flair text: {e}")

                                if not chosen:
                                    print(f"⚠️ No flair '{desired_flair}' found. Choosing a random flair.")
                                    random_flair = random.choice(flairs)
                                    try:
                                        random_flair.click()
                                        print("✅ Clicked a random flair")
                                    except Exception as e:
                                        print(f"❌ Failed to click a random flair: {e}")

                                try:
                                    page.click("#post-flair-modal-apply-button", timeout=3000)
                                    print("✅ Clicked the 'Add' button.")
                                except Exception as e:
                                    print(f"⚠️ Failed to click the 'Add' button: {e}")

                            pause_point()
                            time.sleep(1)
                        else:
                            print("⚠️ Flair button not visible – skipping.")
                    except Exception as e:
                        print(f"⚠️ Failed to set the flair: {e}")

                print("Waiting for the title field...")
                page.wait_for_selector("textarea#innerTextArea", timeout=10000)
                page.click("textarea#innerTextArea")
                page.fill("textarea#innerTextArea", "")
                page.type("textarea#innerTextArea", post_data["Tytuł"], delay=random.randint(40, 90))
                print("✅ Title entered naturally.")

                if post_data.get("Tekst"):
                    try:
                        page.wait_for_selector("div[data-testid='post-content']", timeout=5000)
                        page.fill("div[data-testid='post-content']", post_data["Tekst"])
                    except Exception:
                        page.fill("div[role='textbox']", post_data["Tekst"])
                    time.sleep(1)

                if post_data.get("Media"):
                    media = post_data["Media"].strip()

                    if media.startswith("http"):
                        print("🔗 Detected link — switching to the 'Link' tab...")
                        try:
                            page.click('button[data-select-value="LINK"]', timeout=5000)
                            page.wait_for_selector("r-post-url-input-wrapper textarea[name='link']", timeout=10000)
                            delay_before_fill = random.uniform(1, 5)
                            print(f"⏳ Waiting {delay_before_fill:.2f}s before pasting the link...")
                            time.sleep(delay_before_fill)
                            page.fill("r-post-url-input-wrapper textarea[name='link']", media)
                            print("✅ Pasted the link to the post.")
                        except Exception as e:
                            print(f"❌ Failed to paste the link: {e}")
                            return False
                    else:
                        MAX_UPLOAD_RETRIES = 3
                        upload_attempts = 0
                        upload_success = False

                        try:
                            image_tab = page.locator("button[data-select-value='IMAGE']")
                            if image_tab and image_tab.first.is_visible():
                                print("🔄 Clicking the 'Image' tab before upload...")
                                image_tab.first.click()
                                time.sleep(1)
                                page.keyboard.press("PageDown")
                                time.sleep(0.5)
                            else:
                                print("⚠️ 'Image' tab not visible.")
                        except Exception as e:
                            print(f"❌ Error clicking the 'Image' tab: {e}")

                        while upload_attempts < MAX_UPLOAD_RETRIES and not upload_success:
                            upload_attempts += 1
                            try:
                                print(f"📤 Upload attempt {upload_attempts}...")
                                self.simulate_file_upload_in_shadow_dom(page, media, "r-post-media-input#post-composer_media")
                                print("⏳ Waiting for the thumbnail...")
                                page.wait_for_selector("div#fileInputInnerWrapper img", timeout=40000)
                                print("✅ Image uploaded.")
                                upload_success = True
                            except Exception as e:
                                print(f"⚠️ Upload failed (attempt {upload_attempts}): {e}")
                                if upload_attempts < MAX_UPLOAD_RETRIES:
                                    print("🔁 Trying again...")
                                    time.sleep(2)
                                else:
                                    print("⛔ Failed to upload the image after multiple attempts. Skipping this post.")
                                    return False
                try:
                    print("Scrolling and clicking the hidden 'Publish' button in Shadow DOM...")
                    for _ in range(5):
                        page.keyboard.press("PageDown")
                        time.sleep(1)

                    submit_button = page.locator("#submit-post-button >>> button#inner-post-submit-button")
                    time.sleep(3)
                    submit_button.click(force=True)
                    print("✅ Clicked the 'Publish' button.")

                    pause_range = CONFIG.get("pause_after_post", [23, 55])
                    delay_post = random.randint(*pause_range)
                    print(f"⏳ Waiting {delay_post} seconds after publishing before closing the profile...")
                    time.sleep(delay_post)

                    return True
                except Exception as e:
                    print(f"❌ Problem with clicking the 'Publish' button: {e}")
                    return False

        except Exception as e:
            print(f"❌ Error during publishing: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            if browser:
                pass
            self.stop_adspower_profile(user_id)

    def run(self):
        self.email = CONFIG.get("email")
        self.password = CONFIG.get("password")
        self.num_accounts = len(CONFIG.get("ads_power_user_ids", []))

        while True:
            pause_point()



            try:
                if not self.check_remote_auth_via_api(self.email, self.password, self.num_accounts):
                    print("⛔ No authorization — ending program.")
                    return

                available_user_ids = CONFIG["ads_power_user_ids"]
                shuffled_ids = random.sample(available_user_ids, len(available_user_ids))

                post = None
                user_id = None

                print(f"🔍 Searching for available posts – skipping the last used account ({self.last_used_user_id})...")

                for attempt_id in shuffled_ids:
                    if attempt_id != self.last_used_user_id:
                        print(f"👉 Checking account: {attempt_id}")
                        possible_post = self.get_random_unused_post(attempt_id)
                        if possible_post:
                            print(f"✅ Found post for account: {attempt_id}")
                            user_id = attempt_id
                            post = possible_post
                            break
                        else:
                            print(f"❌ No available posts for {attempt_id}")

                if not post and self.last_used_user_id in available_user_ids:
                    print(f"🔁 Trying with the last used account: {self.last_used_user_id}")
                    possible_post = self.get_random_unused_post(self.last_used_user_id)
                    if possible_post:
                        print(f"✅ Successfully found a post on the last used account!")
                        user_id = self.last_used_user_id
                        post = possible_post
                    else:
                        print(f"❌ The last used account ({self.last_used_user_id}) also has no posts.")

                if not post:
                    print("🚫 No posts available for any account.")
                    print("✅ Bot ended work.")
                    break

                reddit_name = self.get_reddit_name_for_user(user_id)
                print(f"👤 Selected account: {user_id} (Reddit: {reddit_name})")
                print(f"🧾 Selected post: {post['Tytuł']} (Subreddit: r/{post['Subreddit']})")

                success = self.post_to_reddit(user_id, post)

                if success:
                    row_index = next(
                        (i for i, row in enumerate(self.sheet_data) if row.get("Tytuł") == post["Tytuł"]),
                        None
                    )

                    if row_index is not None:
                        self.mark_post_as_used(post["Tytuł"])
                        self.sheet_data = self.fetch_sheet_data()
                    else:
                        print("⚠️ No row found with matching title – skipping marking as used.")

                    self.last_used_user_id = user_id

                delay = random.randint(CONFIG["min_delay"], CONFIG["max_delay"])
                print(f"⏳ Next publication in {delay // 60} minutes...")
                pause_point()
                time.sleep(delay)

            except Exception as e:
                print(f"⚠️ Global error: {e}")
                pause_point()
                time.sleep(60)
