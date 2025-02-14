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
    # Debug: Attempting to beep at 550 Hz for 200 ms
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
            # Debug: Could not retrieve window text for this window.
            continue
    return None

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

    If user answers 'yes', we consider this GroupBox to be the feed container.
    (Note: It doesn't have to contain the entire feed, just enough to match
    our heuristic, then the user decides if it's correct.)

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
                continue  # Only check GroupBox elements

            text = ctrl.window_text().strip()
            # Heuristic check: must contain at least one timestamp.
            if text and timestamp_pattern.search(text):
                # Potential candidate
                log(f"[GroupBox] Potential match - Rank: {idx}, Class: {class_name}")
                snippet = text[:300]  # Show part of the text to avoid flooding
                log("Detected text snippet:")
                log(f"{'='*40}\n{snippet}\n{'='*40}")

                # Ask the user for confirmation
                user_input = input("Is this the correct news feed (GroupBox)? (yes/no): ").strip().lower()
                if user_input == "yes":
                    log("User confirmed this GroupBox as the correct news feed control.")
                    return ctrl, "groupbox"
                else:
                    log("User rejected this GroupBox control. Searching for another match...")

        except Exception as e:
            log(f"[GroupBox] Error accessing control {idx}: {e}")

    # If we exhaust all GroupBox candidates, return None
    log("[GroupBox] No suitable GroupBox control found or all were rejected.")
    return None

def get_news_from_groupbox(ctrl):
    """
    Retrieves the raw text from a confirmed GroupBox control.
    We then extract only the first news item (if there are multiple) by:
      - Searching for multiple timestamps.
      - If multiple timestamps are found, only return text up to the 2nd timestamp.

    Returns:
        str: The text from the first news item, or if only one timestamp is found,
             the entire text from this GroupBox.
    """
    try:
        raw_text = ctrl.window_text().strip()
        log(f"[GroupBox] Raw control text length={len(raw_text)}")
    except Exception as e:
        log(f"[GroupBox] Error retrieving text from control: {e}")
        return ""

    # Extract only the first news item if there's more than one timestamp.
    return extract_first_news_item(raw_text)


def extract_first_news_item(text):
    """
    Given a block of text that might contain multiple news items (each marked by timestamps),
    return only the first news item.

    If two or more timestamps are found, return the substring up to the second timestamp.
    Otherwise, return the entire text.
    """
    pattern = re.compile(r'\b\d{2}:\d{2}:\d{2}\b')
    matches = list(pattern.finditer(text))
    if len(matches) >= 2:
        # Return text from start up to the second timestamp
        return text[:matches[1].start()].strip()
    return text.strip()

###################################################################
# Static Approach
###################################################################
def find_and_confirm_statics(window):
    """
    Fallback approach if no suitable GroupBox is found or user rejects them.

    This function:
      1) Pairs Static controls: the first with a strict 'XX:XX:XX' timestamp,
         the next presumably with ALL-CAPS headline text.
      2) Merges each pair into a single line "HH:MM:SS HEADLINE".
      3) Shows the assembled text snippet and asks for user confirmation.

    If user answers 'yes', it returns ("static", True).
    Otherwise, returns None.

    Args:
        window: The main FIATFEED pywinauto window reference.

    Returns:
        ("static", True) if user confirms,
        None if user rejects or no text is assembled.
    """
    log("Attempting Static-based feed detection...")
    assembled_text = assemble_news_from_statics(window)
    if not assembled_text.strip():
        log("[Static] No text was assembled. Possibly no timestamp in Static controls.")
        return None

    # Show user a snippet for confirmation
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
    Scans the window's 'Static' controls in order. For every pair:
      1) The first is a strict timestamp (^\d{2}:\d{2}:\d{2}$),
      2) The second is presumably the ALL-CAPS headline.

    Merges each pair into one line: "HH:MM:SS HEADLINE_IN_CAPS".
    Returns a multi-line string containing all detected pairs.

    This function is not interactive; it only returns the assembled text.
    """
    controls = window.descendants()
    timestamp_pattern = re.compile(r'^\d{2}:\d{2}:\d{2}$')  # Strict: must match exactly

    assembled_lines = []
    i = 0
    while i < len(controls):
        ctrl = controls[i]
        try:
            class_name = ctrl.friendly_class_name()
            text = ctrl.window_text().strip()
        except Exception:
            i += 1
            continue

        if class_name == "Static":
            # Check if the static text is a timestamp
            if timestamp_pattern.match(text):
                # Look for the next 'Static' for the headline text
                if i + 1 < len(controls):
                    next_ctrl = controls[i + 1]
                    try:
                        next_class_name = next_ctrl.friendly_class_name()
                        next_text = next_ctrl.window_text().strip()
                    except Exception:
                        next_text = ""
                        next_class_name = "Unknown"

                    if next_class_name == "Static" and next_text:
                        # Merge them: timestamp + text
                        assembled_lines.append(f"{text} {next_text}")
                        i += 2  # Skip the next control as well
                        continue
        i += 1

    return "\n".join(assembled_lines)

def get_news_from_statics(window):
    """
    Builds the entire feed from statics every time we query it.
    We'll rely on diffing (via difflib) to detect any new lines.

    Returns:
        str: Concatenated lines from Static pairs, each on a new line.
    """
    text = assemble_news_from_statics(window)
    return text.strip()

###################################################################
# Monitoring Logic
###################################################################
def monitor_fiatfeed_window():
    """
    Monitors the FIATFEED window for news updates, using whichever feed-discovery
    approach was confirmed (GroupBox or Static).

    Steps:
      1) Connect to the FIATFEED window by PID.
      2) Attempt GroupBox approach first:
         - If it finds a candidate GroupBox that user confirms, we stick to that.
         - Otherwise, fallback to Static approach and confirm with user.
      3) Once feed is determined, we poll the feed text for changes:
         - If new lines appear, beep, log, tweet, and write them to CSV.

    If the window is closed at any time, the function returns.
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

    # Attempt GroupBox approach
    feed_control = None
    approach = None

    groupbox_result = find_and_confirm_groupbox(main_window)
    if groupbox_result:
        # groupbox_result is (ctrl, "groupbox")
        feed_control, approach = groupbox_result
    else:
        # Fallback to Static approach
        static_result = find_and_confirm_statics(main_window)
        if static_result:
            approach, _ = static_result  # "static", True
        else:
            log("No suitable feed (GroupBox or Static) confirmed. Exiting.")
            return

    # Initialize last_text by reading from the chosen approach
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

        # Compare newly extracted text with old text
        if current_text and current_text != last_text:
            beep()
            log("News feed updated!")

            # Use difflib to identify new lines
            diff = list(difflib.ndiff(last_text.splitlines(), current_text.splitlines()))
            new_lines = [line[2:] for line in diff if line.startswith('+ ')]
            # Remove duplicates while preserving order
            new_lines = list(dict.fromkeys(new_lines))

            if new_lines:
                # Log, tweet, and store in CSV
                for line in new_lines:
                    log(f"New line: {line}")
                    try:
                        publisher.post_to_twitter(line)
                    except Exception as post_err:
                        log(f"Error posting to Twitter: {post_err}")

                # Write new lines to CSV with timestamp
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

###################################################################
# Main Entry Point
###################################################################
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
