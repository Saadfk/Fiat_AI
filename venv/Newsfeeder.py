import time
import winsound
import difflib
import re
import csv
import datetime
from pywinauto import Application, Desktop
import publisher

POLL_INTERVAL = 0.5  # seconds
TARGET_CONTROL_RANK = 117  # Adjust this index as needed


def beep():
    """Play a beep sound."""
    winsound.Beep(550, 200)


def find_fiatfeed_pid():
    """
    Scans all top-level windows and returns the PID of the first window
    whose title contains "FIATFEED".
    """
    for window in Desktop(backend="uia").windows():
        try:
            if "FIATFEED" in window.window_text():
                pid = window.process_id()
                print(f"Found FIATFEED window: '{window.window_text()}' with PID: {pid}")
                return pid
        except Exception:
            continue
    return None


def extract_first_news_item(text):
    """
    Extracts the first news item from the given text using a time stamp heuristic.
    It looks for the second occurrence of a time stamp (format: xx:xx:xx) and
    returns text up to that point.
    """
    pattern = re.compile(r'\b\d{2}:\d{2}:\d{2}\b')
    matches = list(pattern.finditer(text))
    if len(matches) >= 2:
        return text[:matches[1].start()].strip()
    return text.strip()


def yield_descendants(element):
    """
    Recursively yields descendant controls of the given element.
    """
    try:
        children = element.children()
    except Exception:
        children = []
    for child in children:
        yield child
        yield from yield_descendants(child)


def get_nth_descendant(window, target_index):
    """
    Returns the descendant control at the specified target index.
    """
    for count, ctrl in enumerate(yield_descendants(window)):
        if count == target_index:
            return ctrl
    return None


def get_news_feed_text(window, debug=False):
    """
    Retrieves text from the control at rank TARGET_CONTROL_RANK,
    then extracts the first news item using the heuristic based on time stamps.

    If debug is True, detailed information (control rank, class, and text)
    for all 'Static' or 'GroupBox' controls are written to 'debug_controls.csv'.
    """
    if debug:
        controls = window.descendants()
        debug_filename = "debug_controls.csv"
        with open(debug_filename, "w", newline='', encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Rank", "Class", "Text"])
            for i, ctrl in enumerate(controls):
                try:
                    class_name = ctrl.friendly_class_name()
                except Exception:
                    class_name = "Unknown"
                if class_name not in ("Static", "GroupBox"):
                    continue
                try:
                    text = ctrl.window_text().strip()
                except Exception:
                    text = ""
                writer.writerow([i, class_name, text])
        print(f"Debug information written to {debug_filename}.")
        if len(controls) <= TARGET_CONTROL_RANK:
            print(f"Warning: Not enough controls to access rank {TARGET_CONTROL_RANK}.")
            return ""
        try:
            headline_text = controls[TARGET_CONTROL_RANK].window_text().strip()
        except Exception as e:
            print(f"Error retrieving text from rank {TARGET_CONTROL_RANK}: {e}")
            return ""
    else:
        ctrl = get_nth_descendant(window, TARGET_CONTROL_RANK)
        if ctrl is None:
            print(f"Warning: Not enough controls to access rank {TARGET_CONTROL_RANK}.")
            return ""
        try:
            headline_text = ctrl.window_text().strip()
        except Exception as e:
            print(f"Error retrieving text from rank {TARGET_CONTROL_RANK}: {e}")
            return ""

    return extract_first_news_item(headline_text)


def monitor_fiatfeed_window():
    """
    Monitors the FIATFEED window for news updates. When a change is detected,
    it beeps, posts new lines to Twitter, and appends each new line with a timestamp
    to 'fiatfeed_news.csv'.
    """
    pid = find_fiatfeed_pid()
    if not pid:
        print("FIATFEED window not found. Exiting monitoring function.")
        return

    try:
        app = Application(backend="uia").connect(process=pid)
        main_window = app.window(title="FIATFEED")
        print("FIATFEED window attached. Window text:", main_window.window_text())
    except Exception as e:
        print("Error attaching to FIATFEED window:", e)
        return

    print("Waiting for the UI to populate...")
    time.sleep(3)  # Allow extra time for the UI to load completely

    last_text = get_news_feed_text(main_window)
    print("Monitoring news feed text for changes...")

    while True:
        time.sleep(POLL_INTERVAL)
        try:
            current_text = get_news_feed_text(main_window)
        except Exception as e:
            print("Error retrieving aggregated text:", e)
            break

        if current_text and current_text != last_text:
            beep()
            print("News feed updated!")
            diff = list(difflib.ndiff(last_text.splitlines(), current_text.splitlines()))
            new_lines = [line[2:] for line in diff if line.startswith('+ ')]
            # Remove duplicates while preserving order.
            new_lines = list(dict.fromkeys(new_lines))
            if new_lines:
                print("New text:")
                for line in new_lines:
                    print(line)
                    publisher.post_to_twitter(line)
                with open("fiatfeed_news.csv", "a", newline="", encoding="utf-8") as csvfile:
                    writer = csv.writer(csvfile)
                    for line in new_lines:
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        writer.writerow([timestamp, line])
            else:
                print("Update detected, but no new lines could be isolated.")
        else:
            print("No change detected.")

        last_text = current_text


def main():
    """
    Continuously monitors for the FIATFEED window. If found, it starts monitoring;
    if the window is lost, it waits and retries.
    """
    print("Starting FIATFEED auto-monitor. Waiting for FIATFEED window to appear...")
    while True:
        pid = find_fiatfeed_pid()
        if pid:
            print("FIATFEED window detected. Starting monitoring...")
            monitor_fiatfeed_window()
            print("Monitoring stopped. Waiting for FIATFEED window to reappear...")
        else:
            print("FIATFEED window not found. Retrying in 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    main()
