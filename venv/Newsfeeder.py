import time
import winsound
import csv
import datetime
import logging
from pywinauto import Application, Desktop
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

###################################################################
# Logging Setup
###################################################################
logging.basicConfig(
    filename="fiatfeed_monitor.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)


def log(message):
    """
    Prints a message to the console and also logs it to fiatfeed_monitor.log.
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


def dump_controls_to_csv(window, filename="all_controls_debug.csv"):
    """
    Enumerates all controls in 'window' and writes them to a CSV:
      Rank, ClassName, ControlText
    This helps you see which index each control has.
    """
    log(f"Dumping all controls to CSV: {filename} ...")
    controls = window.descendants()
    try:
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Rank", "ClassName", "ControlText"])
            for i, ctrl in enumerate(controls):
                try:
                    class_name = ctrl.friendly_class_name()
                except Exception:
                    class_name = "Unknown"
                try:
                    text = ctrl.window_text().strip()
                except Exception:
                    text = ""
                writer.writerow([i, class_name, text])
        log(f"Control dump completed. Found {len(controls)} total controls.")
    except Exception as e:
        log(f"Error writing debug CSV: {e}")


def pick_control_by_rank(window):
    """
    Asks the user which rank they want to monitor.
    The user can consult all_controls_debug.csv to find the rank.
    If 'cancel', returns None.
    """
    controls = window.descendants()

    while True:
        rank_str = input("Enter the rank (0-based index) of the control to monitor (or 'cancel'): ").strip().lower()
        if rank_str == "cancel":
            return None

        try:
            rank = int(rank_str)
            if 0 <= rank < len(controls):
                control = controls[rank]
                log(f"Selected control rank {rank}.")

                # Log some info for confirmation
                class_name = "Unknown"
                try:
                    class_name = control.friendly_class_name()
                except Exception:
                    pass

                text_preview = ""
                try:
                    text_preview = control.window_text().strip()
                except Exception:
                    pass

                log(f"Control info -> Class: {class_name}, Text snippet: {text_preview[:200]}")

                confirm = input("Is this the correct control to monitor? (yes/no): ").strip().lower()
                if confirm == "yes":
                    log(f"User confirmed control rank {rank} for monitoring.")
                    return control
                else:
                    log(f"User rejected control rank {rank}.")
            else:
                log(f"Invalid rank: {rank}. Must be between 0 and {len(controls) - 1}.")
        except ValueError:
            log(f"Could not parse rank: {rank_str}. Please enter a valid integer or 'cancel'.")


###################################################################
# Set-based approach to avoid re-logging lines we already saw
###################################################################
# Regular expression to remove a leading timestamp (format HH:MM:SS)
time_regex = re.compile(r"^\d{2}:\d{2}:\d{2}\s+(.*)")

import re

def extract_latest_headline(full_text):
    """
    Given the full text of the control, split it into lines and return the first line
    that starts with a timestamp (e.g., "03:17:43"). Returns None if no such line is found.
    """
    for line in full_text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Check if the line begins with a timestamp in the format HH:MM:SS
        m = re.match(r"^\d{2}:\d{2}:\d{2}\s+(.*)", line)
        if m:
            return m.group(1).strip()
    return None


def monitor_control(control, main_window):
    """
    Polls 'control' for text changes every POLL_INTERVAL.
    It uses extract_latest_headline() to extract the headline (i.e. the first line with a timestamp).
    """
    last_headline = None
    spinner_frames = ['|', '/', '-', '\\']
    spinner_index = 0

    # Initialize last_headline using the current control text.
    try:
        initial_text = control.window_text()
        last_headline = extract_latest_headline(initial_text)
    except Exception as e:
        log(f"Error retrieving initial text from control: {e}")

    log("Beginning to monitor this control for new headlines...")

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

        current_headline = extract_latest_headline(current_text)
        if current_headline is None:
            # If we couldn't extract a headline, continue monitoring.
            continue

        if current_headline != last_headline:
            beep()
            log(f"New headline detected: {current_headline}")
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open("fiatfeed_news.csv", "a", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([stamp, current_headline])
            last_headline = current_headline
        else:
            # Show a spinner to indicate activity
            spinner_char = spinner_frames[spinner_index]
            print(f"Monitoring {spinner_char}", end='\r', flush=True)
            spinner_index = (spinner_index + 1) % len(spinner_frames)



def monitor_fiatfeed_window():
    """
    Main routine:
      1) Attach to FIATFEED window.
      2) Dump controls to debug CSV so you can see them.
      3) Prompt for which rank to monitor.
      4) Monitor that control, logging only brand-new lines we haven't seen before.
    """
    pid = find_fiatfeed_pid()
    if not pid:
        log(f"No window found matching '{WINDOW_TITLE}'. Exiting.")
        return

    try:
        app = Application(backend="uia").connect(process=pid)
        main_window = app.window(title=WINDOW_TITLE)
        log(f"Attached to '{WINDOW_TITLE}' window successfully.")
    except Exception as e:
        log(f"Error attaching to '{WINDOW_TITLE}' window: {e}")
        return

    log("Waiting a moment for the UI to populate...")
    time.sleep(2)

    dump_controls_to_csv(main_window, filename="all_controls_debug.csv")

    control = pick_control_by_rank(main_window)
    if not control:
        log("No control chosen; exiting.")
        return

    monitor_control(control, main_window)


def main():
    """
    Keeps checking for the FIATFEED window every 5 seconds.
    Once found, do the routine and wait until it ends.
    """
    log(f"Starting {WINDOW_TITLE} auto-monitor. Waiting for '{WINDOW_TITLE}' window to appear...")

    while True:
        pid = find_fiatfeed_pid()
        if pid:
            log(f"Detected '{WINDOW_TITLE}' window. Beginning monitoring routine...")
            monitor_fiatfeed_window()
            log("Monitoring ended. Will wait for window to reappear...")
        else:
            log(f"'{WINDOW_TITLE}' window not found. Retrying in 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    main()
