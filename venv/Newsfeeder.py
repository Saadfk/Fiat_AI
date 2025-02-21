import time
import winsound
import csv
import datetime
import logging
import re
import requests
from pywinauto import Application, Desktop
from Keys import DISCORD_BOT_TOKEN, NOTEBOOK_CHANNEL_ID

# Configuration constants
POLL_INTERVAL = 0.5
WINDOW_TITLE = "FIATFEED"
MAX_ATTEMPTS = 10

# Logging setup
logging.basicConfig(
    filename="fiatfeed_monitor.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

def log(message):
    """Log a message to console and file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    logging.info(message)

def beep():
    """Play a beep sound to signal an update."""
    winsound.Beep(550, 200)

def find_fiatfeed_pid():
    """Return the PID of the window containing WINDOW_TITLE."""
    for w in Desktop(backend="uia").windows():
        try:
            if WINDOW_TITLE in w.window_text():
                pid = w.process_id()
                log(f"Found '{w.window_text()}' with PID {pid}.")
                return pid
        except Exception:
            continue
    return None

# --- Headline Extraction ---

def is_all_upper(text):
    """Return True if all alphabetic characters are uppercase."""
    filtered = ''.join(c for c in text if c.isalpha())
    return bool(filtered) and filtered == filtered.upper()

def words_mostly_upper(text, threshold=0.75):
    """Return True if at least threshold fraction of words are fully uppercase."""
    words = text.split()
    if not words:
        return False, 0.0
    count = sum(1 for word in words if ''.join(c for c in word if c.isalpha()) == ''.join(c for c in word if c.isalpha()).upper())
    ratio = count / len(words)
    return ratio >= threshold, ratio

def extract_headline(full_text):
    """
    Extract the first headline candidate from full_text.
    A candidate is defined as text following a timestamp (HH:MM:SS) that has at least 5 words
    and is either entirely uppercase or at least 75% uppercase.
    """
    pattern = re.compile(r'(\d{2}:\d{2}:\d{2})\s+((?:(?!\d{2}:\d{2}:\d{2}).)+)', re.DOTALL)
    candidates = pattern.findall(full_text)
    for _, candidate in candidates:
        candidate = candidate.strip()
        if len(candidate.split()) < 5:
            continue
        if is_all_upper(candidate):
            return candidate
        passes, _ = words_mostly_upper(candidate, threshold=0.75)
        if passes:
            return candidate
    return None

# --- Discord and CSV Logging ---

def post_to_discord(message):
    """Post the given message to the Discord channel using the Bot token."""
    url = f"https://discord.com/api/v9/channels/{NOTEBOOK_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"content": message}
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except Exception as e:
        log(f"Failed to post to Discord: {e}")

def log_headline_to_csv(headline):
    """Append a timestamped headline to headlines.csv."""
    with open("headlines.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), headline])

# --- Monitoring Routine ---

def monitor_control(control, main_window):
    """Poll the control for updates, extract headlines, log and post them."""
    spinner_frames = ['|', '/', '-', '\\']
    spinner_index = 0
    seen_lines = set()

    try:
        initial_text = control.window_text()
        seen_lines.update(line for line in initial_text.splitlines() if line.strip())
    except Exception as e:
        log(f"Error reading initial text: {e}")

    log("Monitoring control for updates...")
    while True:
        time.sleep(POLL_INTERVAL)
        if not main_window.exists():
            log(f"Window '{WINDOW_TITLE}' no longer exists. Stopping monitoring.")
            break
        try:
            current_text = control.window_text()
        except Exception as e:
            log(f"Error reading control: {e}")
            break

        current_lines = [line for line in current_text.splitlines() if line.strip()]
        new_lines = [ln for ln in current_lines if ln not in seen_lines]
        for ln in new_lines:
            seen_lines.add(ln)

        if new_lines:
            beep()
            # Dump complete control text for later analysis
            try:
                with open("control_dump.csv", "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                    for line in current_text.splitlines():
                        writer.writerow([line])
                    writer.writerow([])  # separator
            except Exception as e:
                log(f"Error dumping control text: {e}")

            headline = extract_headline(current_text)
            if headline:
                log(f"Extracted headline: {headline}")
                log_headline_to_csv(headline)
                #post_to_discord(headline)
            else:
                log("No valid headline extracted.")
        else:
            print(f"Monitoring {spinner_frames[spinner_index]}", end='\r', flush=True)
            spinner_index = (spinner_index + 1) % len(spinner_frames)

def monitor_fiatfeed_window():
    """Attach to the FIATFEED window, select control, and start monitoring."""
    pid = find_fiatfeed_pid()
    if not pid:
        log(f"No window found matching '{WINDOW_TITLE}'. Exiting.")
        return

    # if input(f"Found FIATFEED window with PID {pid}. Proceed? (yes/no): ").strip().lower() != "yes":
    #     log("User canceled. Exiting.")
    #     return

    try:
        app = Application(backend="uia").connect(process=pid)
        main_window = app.window(title_re=".*" + WINDOW_TITLE + ".*")
    except Exception as e:
        log(f"Error attaching to window: {e}")
        return

    time.sleep(2)  # Allow UI to populate
    try:
        controls = main_window.descendants()
        if len(controls) > 3:
            control = controls[3]
        else:
            log("Not enough controls found to select rank 3. Exiting.")
            return
    except Exception as e:
        log(f"Error selecting control: {e}")
        return

    monitor_control(control, main_window)

def main():
    """Main loop: monitor FIATFEED window and reconnect if necessary."""
    log(f"Starting {WINDOW_TITLE} auto-monitor.")
    attempts = 0
    while attempts < MAX_ATTEMPTS:
        pid = find_fiatfeed_pid()
        if pid:
            monitor_fiatfeed_window()
            attempts = 0  # Reset on success
        else:
            attempts += 1
            log(f"Window '{WINDOW_TITLE}' not found. Attempt {attempts}/{MAX_ATTEMPTS}.")
        time.sleep(5)
    log("Max attempts reached. Exiting monitor.")

if __name__ == "__main__":
    main()
