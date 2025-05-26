from bot.reddit import RedditAutomation
import functools
import os
import time

# 🔄 Printy lecą od razu do stdout, więc Tauri je przechwyci
print = functools.partial(print, flush=True)

# 🔂 Ścieżka do pliku pauzy
PAUSE_FILE = os.path.abspath("pause.flag")

def wait_if_paused():
    if not os.path.exists(PAUSE_FILE):
        return  # nie wypisuj nic

    print("⏸️ Bot paused...")
    while os.path.exists(PAUSE_FILE):
        time.sleep(1)
    print("▶️ Bot resumed.")


if __name__ == "__main__":
    wait_if_paused()
    bot = RedditAutomation()
    bot.run()
