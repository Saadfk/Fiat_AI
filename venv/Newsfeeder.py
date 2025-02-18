import time
import winsound
import csv
import datetime
import logging
import re
from pywinauto import Application, Desktop

###################################################################
# Configuration
###################################################################
POLL_INTERVAL = 0.5  # seconds between checks for feed updates
WINDOW_TITLE = "FIATFEED"  # Title substring for the FIATFEED window

# Maximum number of attempts for reconnecting to the FIATFEED window
MAX_ATTEMPTS = 10

###################################################################
# Logging Setup (only one instance now)
###################################################################
logging.basicConfig(
    filename="fiatfeed_monitor.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)


def log(message):
    """
    Prints a message to the console and also logs it.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    logging.info(message)


###################################################################
# Utility Functions
###################################################################
def beep():
    """Plays a short beep sound to indicate a news feed update."""
    winsound.Beep(550, 200)


def find_fiatfeed_pid():
    """
    Scans all top-level windows and returns the PID of the first one
    whose title contains WINDOW_TITLE.
    """
    for w in Desktop(backend="uia").windows():
        try:
            if WINDOW_TITLE in w.window_text():
                pid = w.process_id()
                log(f"Found {WINDOW_TITLE} window: '{w.window_text()}' with PID: {pid}")
                return pid
        except Exception:
            continue
    return None


###################################################################
# Headline Extraction Helper Functions
###################################################################
def is_all_upper(text):
    """
    Returns True if all alphabetic characters in text are uppercase.
    Non-alphabetic characters are ignored.
    """
    filtered = ''.join(c for c in text if c.isalpha())
    return bool(filtered) and (filtered == filtered.upper())


def words_mostly_upper(text, threshold=0.75):
    """
    Splits text into words, removes non-alpha characters from each,
    and returns a tuple (bool, ratio) where bool indicates whether at least
    'threshold' fraction of the words are entirely uppercase.
    """
    words = text.split()
    if not words:
        return False, 0.0
    count = 0
    for word in words:
        clean = ''.join(c for c in word if c.isalpha())
        if clean and (clean == clean.upper()):
            count += 1
    ratio = count / len(words)
    return (ratio >= threshold), ratio


def extract_headline(full_text):
    """
    Extracts the first headline candidate from full_text that matches our heuristic.

    Instead of relying on newline splits, it uses a regex to locate any timestamp
    (in the form HH:MM:SS) followed by text until the next timestamp.

    For each candidate:
      - It is rejected if it has fewer than 5 words.
      - It is accepted immediately if all alphabetic characters are uppercase.
      - Otherwise, if at least 75% of its words are entirely uppercase, it is accepted.

    Detailed logging is performed for each candidate.
    """
    import re
    # This pattern finds a timestamp followed by any text until the next timestamp.
    pattern = re.compile(r'(\d{2}:\d{2}:\d{2})\s+((?:(?!\d{2}:\d{2}:\d{2}).)+)', re.DOTALL)
    candidates = pattern.findall(full_text)

    for timestamp, candidate in candidates:
        candidate = candidate.strip()
        words = candidate.split()
        log(f"Candidate from timestamp {timestamp}: '{candidate}' | Word count: {len(words)}")
        if len(words) < 5:
            log("Candidate rejected: less than 5 words.")
            continue

        if is_all_upper(candidate):
            log("Candidate accepted via is_all_upper check.")
            return candidate

        passes, ratio = words_mostly_upper(candidate, threshold=0.75)
        log(f"Candidate uppercase word ratio: {ratio:.2f}")
        if passes:
            log("Candidate accepted via words_mostly_upper check.")
            return candidate
        else:
            log("Candidate rejected: not enough uppercase words.")

    log("extract_headline: No headline matching the heuristic was found.")
    return None


###################################################################
# Revised Monitoring Function
###################################################################
def monitor_control(control, main_window):
    """
    Continuously polls 'control' for text changes every POLL_INTERVAL.
    On detecting any new lines, beeps, logs them, and dumps the entire control text
    to control_dump.csv for debugging. Also tries to extract a headline using the heuristic.
    """
    spinner_frames = ['|', '/', '-', '\\']
    spinner_index = 0
    seen_lines = set()

    # Initialize seen_lines with the current control text.
    try:
        initial_text = control.window_text()
        for line in initial_text.splitlines():
            if line.strip():
                seen_lines.add(line)
    except Exception as e:
        log(f"Error retrieving initial text from control: {e}")

    log("Beginning to monitor this control for new lines (beep on any change)...")

    while True:
        time.sleep(POLL_INTERVAL)

        if not main_window.exists():
            log(f"Window '{WINDOW_TITLE}' no longer exists. Stopping monitoring.")
            break

        try:
            current_text = control.window_text()
        except Exception as e:
            log(f"Unable to read from control (probably destroyed): {e}")
            break

        # Detect new lines using a set-based approach.
        current_lines = [line for line in current_text.splitlines() if line.strip()]
        new_lines = [ln for ln in current_lines if ln not in seen_lines]
        for ln in new_lines:
            seen_lines.add(ln)

        if new_lines:
            beep()
            log("Feed text changed! Newly found lines:")
            for ln in new_lines:
                log(f"[NEW] {ln}")
            # Dump the entire control text to control_dump.csv for debugging
            try:
                with open("control_dump.csv", "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                    for line in current_text.splitlines():
                        writer.writerow([line])
                    writer.writerow([])  # Separator row
                log("Control text dumped to control_dump.csv")
            except Exception as e:
                log(f"Error dumping control text: {e}")

            # Attempt to extract a headline (heuristic may need further adjustment)
            headline = extract_headline(current_text)
            if headline:
                log(f"Extracted headline: {headline}")
            else:
                log("No valid headline extracted using the heuristic.")
        else:
            # Display a spinner to indicate activity.
            spinner_char = spinner_frames[spinner_index]
            print(f"Monitoring {spinner_char}", end='\r', flush=True)
            spinner_index = (spinner_index + 1) % len(spinner_frames)


###################################################################
# Window Monitoring Routine
###################################################################
def monitor_fiatfeed_window():
    """
    Main routine:
      1) Attaches to the FIATFEED window.
      2) Confirms the PID with the user.
      3) Automatically selects control rank 3.
      4) Monitors that control for changes.
    """
    pid = find_fiatfeed_pid()
    if not pid:
        log(f"No window found matching '{WINDOW_TITLE}'. Exiting.")
        return

    # Confirm the PID with the user
    confirm = input(f"Found FIATFEED window with PID {pid}. Proceed? (yes/no): ").strip().lower()
    if confirm != "yes":
        log("User did not confirm PID. Exiting monitoring routine.")
        return

    try:
        app = Application(backend="uia").connect(process=pid)
        main_window = app.window(title_re=".*" + WINDOW_TITLE + ".*")
        log(f"Attached to '{WINDOW_TITLE}' window successfully.")
    except Exception as e:
        log(f"Error attaching to '{WINDOW_TITLE}' window: {e}")
        return

    log("Waiting a moment for the UI to populate...")
    time.sleep(2)

    # Automatically select control rank 3
    try:
        controls = main_window.descendants()
        if len(controls) > 3:
            control = controls[3]
            log("Automatically selected default control at rank 3.")
        else:
            log("Not enough controls found to select rank 3. Exiting.")
            return
    except Exception as e:
        log(f"Error selecting default control: {e}")
        return

    monitor_control(control, main_window)


###################################################################
# Main Routine with Graceful Reconnection
###################################################################
def main():
    """
    Keeps checking for the FIATFEED window every 5 seconds.
    If found, confirms with the user and runs the monitoring routine.
    If the window is not found for MAX_ATTEMPTS consecutive times, exits.
    """
    log(f"Starting {WINDOW_TITLE} auto-monitor. Waiting for '{WINDOW_TITLE}' window to appear...")
    attempts = 0
    while attempts < MAX_ATTEMPTS:
        pid = find_fiatfeed_pid()
        if pid:
            log(f"Detected '{WINDOW_TITLE}' window. Beginning monitoring routine...")
            monitor_fiatfeed_window()
            log("Monitoring ended. Will wait for window to reappear...")
            attempts = 0  # reset attempts after a successful connection
        else:
            attempts += 1
            log(f"'{WINDOW_TITLE}' window not found. Retrying in 5 seconds... (Attempt {attempts}/{MAX_ATTEMPTS})")
        time.sleep(5)
    log("Max attempts reached. Exiting the monitor.")


if __name__ == "__main__":
    main()
