import time
import winsound
import difflib
import re
import csv
import datetime
import logging
from pywinauto import Application, Desktop
import publisher

###################################################################
# Configuration
###################################################################
POLL_INTERVAL = 0.5  # seconds to wait between checks for feed updates

###################################################################
# Logging Setup
###################################################################
logging.basicConfig(
    filename="fiatfeed_monitor.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def log(message):
    """
    Prints a message to console and also logs it to fiatfeed_monitor.log.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    logging.info(message)

###################################################################
# Utility Functions
###################################################################
def beep():
    """
    Play a short beep sound to indicate a news feed update.
    """
    winsound.Beep(550, 200)

def find_fiatfeed_pid():
    """
    Scans all top-level windows and returns the PID of the first window
    whose title contains 'FIATFEED'.

    Returns:
        PID (int) if found, otherwise None.
    """
    for window in Desktop(backend="uia").windows():
        try:
            if "FIATFEED" in window.window_text():
                pid = window.process_id()
                log(f"Found FIATFEED window: '{window.window_text()}' with PID: {pid}")
                return pid
        except Exception:
            continue
    return None

def dump_all_controls_to_csv(window, filename="all_controls_debug.csv"):
    """
    Enumerates all controls in the specified window (descendants)
    and writes a CSV file with columns: Rank, Class, Text.

    This is useful for diagnosing why the script might not find
    the desired control (e.g., missing GroupBox or Static).
    """
    log(f"Dumping all controls to CSV: {filename} ...")
    try:
        controls = window.descendants()
        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Rank", "ClassName", "ControlText"])
            for idx, ctrl in enumerate(controls):
                try:
                    class_name = ctrl.friendly_class_name()
                except Exception:
                    class_name = "Unknown"

                try:
                    text = ctrl.window_text().strip()
                except Exception:
                    text = ""

                writer.writerow([idx, class_name, text])
        log(f"Control dump completed. Found {len(controls)} total controls.")
    except Exception as e:
        log(f"Error dumping controls to CSV: {e}")

###################################################################
# GroupBox Approach
###################################################################
def find_and_confirm_groupbox(window):
    """
    Scans for the FIRST 'GroupBox' control that contains at least one timestamp
    of the format XX:XX:XX (the heuristic).

    For each match:
      1) Displays a snippet of the text in the console,
      2) Asks the user for confirmation.

    Returns:
        A tuple: (control, "groupbox") if confirmed,
        or None if none match / user rejects them.
    """
    log("Attempting GroupBox-based feed detection...")
    timestamp_pattern = re.compile(r'\b\d{2}:\d{2}:\d{2}\b')
    controls = window.descendants()

    log(f"[GroupBox] Found {len(controls)} total controls to scan.")
    for idx, ctrl in enumerate(controls):
        try:
            class_name = ctrl.friendly_class_name()
            if class_name != "GroupBox":
                continue

            text = ctrl.window_text().strip()
            # Heuristic check: must contain at least one timestamp.
            if text and timestamp_pattern.search(text):
                log(f"[GroupBox] Potential match - Rank: {idx}, Class: {class_name}")
                snippet = text[:300]
                log("Detected text snippet:")
                log(f"{'='*40}\n{snippet}\n{'='*40}")

                user_input = input("Is this the correct news feed (GroupBox)? (yes/no): ").strip().lower()
                if user_input == "yes":
                    log("User confirmed this GroupBox as the correct news feed control.")
                    return ctrl, "groupbox"
                else:
                    log("User rejected this GroupBox control. Searching for another match...")

        except Exception as e:
            log(f"[GroupBox] Error accessing control {idx}: {e}")

    log("[GroupBox] No suitable GroupBox control found or all were rejected.")
    return None

def get_news_from_groupbox(ctrl):
    """
    Retrieves the raw text from a confirmed GroupBox control.
    Then extracts only the first news item if multiple are found.
    """
    try:
        raw_text = ctrl.window_text().strip()
        log(f"[GroupBox] Raw control text length={len(raw_text)}")
    except Exception as e:
        log(f"[GroupBox] Error retrieving text from control: {e}")
        return ""

    return extract_first_news_item(raw_text)

def extract_first_news_item(text):
    """
    If multiple timestamps are found, return text up to the second one;
    otherwise return everything.
    """
    pattern = re.compile(r'\b\d{2}:\d{2}:\d{2}\b')
    matches = list(pattern.finditer(text))
    if len(matches) >= 2:
        return text[:matches[1].start()].strip()
    return text.strip()

###################################################################
# Static Approach
###################################################################
def find_and_confirm_statics(window):
    """
    Fallback if GroupBox approach fails.
    1) Pairs Static controls: the first with a 'XX:XX:XX' timestamp,
       then skipping any non-static controls until we find the next Static
       that presumably contains the headline.
    2) Assembles them: 'HH:MM:SS HEADLINE'
    3) Asks user for confirmation.
    """
    log("Attempting Static-based feed detection...")
    assembled_text = assemble_news_from_statics(window)
    if not assembled_text.strip():
        log("[Static] No text was assembled. Possibly no timestamp in Static controls.")
        return None

    snippet = assembled_text[:300]
    log("[Static] Assembled text snippet:")
    log(f"{'='*40}\n{snippet}\n{'='*40}")

    user_input = input("Is this the correct news feed (Static)? (yes/no): ").strip().lower()
    if user_input == "yes":
        log("User confirmed the Static-based approach.")
        return "static", True
    else:
        log("User rejected the Static-based approach.")
        return None

def assemble_news_from_statics(window):
    """
    NEW LOGIC:
      - We look for a 'Static' control whose text matches ^\d{2}:\d{2}:\d{2}$
      - Then skip forward any number of controls that are NOT 'Static'
        until we reach the next 'Static' containing the headline text.
      - Merge them into "HH:MM:SS HEADLINE".
      - Continue scanning the list of controls in the order they appear.
    """
    controls = window.descendants()
    timestamp_pattern = re.compile(r'^\d{2}:\d{2}:\d{2}$')

    assembled_lines = []
    i = 0
    while i < len(controls):
        ctrl = controls[i]
        # Attempt to read class and text
        try:
            class_name = ctrl.friendly_class_name()
            text = ctrl.window_text().strip()
        except Exception:
            i += 1
            continue

        # If this static is a timestamp, skip forward to find the next static
        if class_name == "Static" and timestamp_pattern.match(text):
            # Found potential timestamp
            time_stamp = text
            # Move forward from i+1 until we find another 'Static'
            # or run out of controls
            j = i + 1
            headline_text = None

            while j < len(controls):
                try:
                    next_class = controls[j].friendly_class_name()
                    next_text = controls[j].window_text().strip()
                except Exception:
                    next_class = "Unknown"
                    next_text = ""

                if next_class == "Static" and next_text:
                    # We treat this as the headline
                    headline_text = next_text
                    # We'll pair time_stamp + headline_text
                    break
                j += 1

            if headline_text:
                assembled_lines.append(f"{time_stamp} {headline_text}")
                # Move 'i' to j+1 so we don't re-scan these
                i = j + 1
                continue
        i += 1

    # Return all assembled lines as multi-line string
    return "\n".join(assembled_lines)

def get_news_from_statics(window):
    """
    Rebuilds the entire feed from static controls every time we query it.
    We'll rely on diffing to detect new lines.
    """
    return assemble_news_from_statics(window).strip()

###################################################################
# Monitoring Logic
###################################################################
def monitor_fiatfeed_window():
    """
    Main monitoring loop:
      1) Attach to the FIATFEED window.
      2) Dump all controls to a CSV (for debugging).
      3) Attempt GroupBox approach -> If fails, fallback to Statics.
      4) Once approach is confirmed, poll for changes.
    """
    pid = find_fiatfeed_pid()
    if not pid:
        log("FIATFEED window not found. Exiting monitoring function.")
        return

    try:
        app = Application(backend="uia").connect(process=pid)
        main_window = app.window(title="FIATFEED")
        log("FIATFEED window attached successfully.")
    except Exception as e:
        log(f"Error attaching to FIATFEED window: {e}")
        return

    log("Waiting for the FIATFEED UI to populate completely...")
    time.sleep(3)

    # Dump controls for debugging
    dump_all_controls_to_csv(main_window, filename="all_controls_debug.csv")

    # Attempt GroupBox approach
    feed_control = None
    approach = None

    groupbox_result = find_and_confirm_groupbox(main_window)
    if groupbox_result:
        feed_control, approach = groupbox_result
    else:
        # Fallback to Static approach
        static_result = find_and_confirm_statics(main_window)
        if static_result:
            approach, _ = static_result
        else:
            log("No suitable feed (GroupBox or Static) confirmed. Exiting.")
            return

    # Initialize last_text
    if approach == "groupbox" and feed_control is not None:
        last_text = get_news_from_groupbox(feed_control)
    else:
        last_text = get_news_from_statics(main_window)

    log("Beginning to monitor the news feed text for changes...")

    while True:
        time.sleep(POLL_INTERVAL)

        try:
            if not main_window.exists():
                log("FIATFEED window no longer exists. Monitoring loop will stop.")
                break

            if approach == "groupbox" and feed_control is not None:
                current_text = get_news_from_groupbox(feed_control)
            else:
                current_text = get_news_from_statics(main_window)
        except Exception as e:
            log(f"Error retrieving text: {e}")
            break

        if current_text and current_text != last_text:
            beep()
            log("News feed updated!")

            diff = list(difflib.ndiff(last_text.splitlines(), current_text.splitlines()))
            new_lines = [line[2:] for line in diff if line.startswith('+ ')]
            new_lines = list(dict.fromkeys(new_lines))  # remove duplicates, keep order

            if new_lines:
                for line in new_lines:
                    log(f"New line: {line}")
                    try:
                        publisher.post_to_twitter(line)
                    except Exception as post_err:
                        log(f"Error posting to Twitter: {post_err}")

                with open("fiatfeed_news.csv", "a", newline="", encoding="utf-8") as csvfile:
                    writer = csv.writer(csvfile)
                    for line in new_lines:
                        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        writer.writerow([stamp, line])
            else:
                log("Update detected, but no new lines could be isolated.")

            last_text = current_text
        else:
            log("No change detected in the news feed.")

def main():
    """
    Continuously monitors the system for the FIATFEED window.
    When found, starts monitoring for text changes.
    If the window goes away, waits and retries every 5 seconds.
    """
    log("Starting FIATFEED auto-monitor. Waiting for FIATFEED window to appear...")

    while True:
        pid = find_fiatfeed_pid()
        if pid:
            log("FIATFEED window detected. Starting monitoring...")
            monitor_fiatfeed_window()
            log("Monitoring stopped. Will wait for FIATFEED window to reappear...")
        else:
            log("FIATFEED window not found. Retrying in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    main()
