import time
import winsound
import difflib
from pywinauto import Application, Desktop
import publisher
import re
import csv

def beep():
    """Plays a beep sound."""
    winsound.Beep(550, 200)


def find_fiatfeed_pid():
    """
    Enumerates all top-level windows and returns the PID of the first window
    whose title contains "FIATFEED".
    """
    for window in Desktop(backend="uia").windows():
        try:
            title = window.window_text()
            if "FIATFEED" in title:
                pid = window.process_id()
                print(f"Found window: '{title}' with PID: {pid}")
                return pid
        except Exception:
            continue
    return None


import csv
import re

def extract_first_news_item(text):
    """
    Extracts the first news item from the given text based on time stamps.
    It looks for the second occurrence of a time stamp in the form xx:xx:xx.
    If found, it returns text from the beginning up to the second time stamp.
    Otherwise, returns the full text.
    """
    pattern = re.compile(r'\b\d{2}:\d{2}:\d{2}\b')
    matches = list(pattern.finditer(text))
    if len(matches) >= 2:
        return text[:matches[1].start()].strip()
    else:
        return text.strip()

def yield_descendants(element):
    """
    A generator that recursively yields descendant controls of the given element.
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
    Walks through the descendant controls using a generator and returns
    the control at the given target index, stopping early if possible.
    """
    count = 0
    for ctrl in yield_descendants(window):
        if count == target_index:
            return ctrl
        count += 1
    return None

def get_news_feed_text(window, debug=False):
    """
    Retrieves the text from the control at rank 119, assumed to contain the news feed headline.
    It further extracts only the first news item using a heuristic based on time stamps.

    If debug is True, it writes details (rank, class, and text) for all controls with class 'Static' or 'GroupBox'
    into a CSV file named 'debug_controls.csv'.

    Parameters:
        window: The window object to inspect.
        debug: A boolean flag to output debug information.

    Returns:
        A string containing the first news item from the control at rank 119.
    """
    target_rank = 117

    if debug:
        # In debug mode, enumerate all controls and write those of interest to a CSV file.
        controls = window.descendants()
        debug_filename = "debug_controls.csv"
        with open(debug_filename, mode="w", newline='', encoding="utf-8") as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(["Rank", "Class", "Text"])
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
                csv_writer.writerow([i, class_name, text])
        print(f"Debug information written to {debug_filename}.")

        if len(controls) <= target_rank:
            print(f"Warning: Not enough controls to access rank {target_rank}.")
            return ""
        try:
            headline_text = controls[target_rank].window_text().strip()
        except Exception as e:
            print(f"Error retrieving text from rank {target_rank}: {e}")
            return ""
    else:
        # In non-debug mode, use the generator to stop as soon as the target control is reached.
        ctrl = get_nth_descendant(window, target_rank)
        if ctrl is None:
            print(f"Warning: Not enough controls to access rank {target_rank}.")
            return ""
        try:
            headline_text = ctrl.window_text().strip()
        except Exception as e:
            print(f"Error retrieving text from rank {target_rank}: {e}")
            return ""

    # Extract only the first news item using the heuristic.
    first_news = extract_first_news_item(headline_text)
    return first_news



def monitor_fiatfeed_window():
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

    # Get the aggregated text from all Static controls
    last_text = get_news_feed_text(main_window)
    print("Monitoring aggregated news feed text for changes...")

    while True:
        time.sleep(0.5)  # Poll every 1 second

        try:
            current_text = get_news_feed_text(main_window)
        except Exception as e:
            print("Error retrieving aggregated text:", e)
            break

        if current_text and current_text != last_text:
            beep()
            print("News feed updated!")

            # Compute the diff between the last and current text.
            diff = list(difflib.ndiff(last_text.splitlines(), current_text.splitlines()))
            new_lines = [line[2:] for line in diff if line.startswith('+ ')]
            # Remove duplicate strings while preserving order.
            new_lines = list(dict.fromkeys(new_lines))
            if new_lines:
                print("New text:")
                for line in new_lines:
                    print(line)
                    publisher.post_to_twitter(line)
            else:
                print("Update detected, but no new lines could be isolated.")


        else:
            print("No change detected.")

        last_text = current_text


def main():
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
