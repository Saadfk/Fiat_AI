import time
import winsound
import difflib
from pywinauto import Application, Desktop
import publisher
import re

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


import re


def extract_first_news_item(text):
    """
    Extracts the first news item from the given text based on time stamps.
    It looks for the second occurrence of a time stamp in the form xx:xx:xx.
    If found, it returns text from the beginning up to the second time stamp.
    Otherwise, returns the full text.
    """
    # Regular expression for a time stamp in the format xx:xx:xx.
    pattern = re.compile(r'\b\d{2}:\d{2}:\d{2}\b')
    matches = list(pattern.finditer(text))
    if len(matches) >= 2:
        # Return text from the start until the start of the second time stamp.
        return text[:matches[1].start()].strip()
    else:
        return text.strip()


def get_news_feed_text(window, debug=False):
    """
    Retrieves the text from the control at rank 262, assumed to contain the news feed headline.
    It further extracts only the first news item using a heuristic based on time stamps.

    If debug is True, it prints details (rank, class, and text) for all controls.

    Parameters:
        window: The window object to inspect.
        debug: A boolean flag to print debug information.

    Returns:
        A string containing the first news item from the control at rank 262.
    """
    controls = window.descendants()

    # Debug mode: list all controls with their rank, class, and text.
    if debug:
        print("Debug: Listing all controls and their details:")
        for i, ctrl in enumerate(controls):
            try:
                class_name = ctrl.friendly_class_name()
            except Exception:
                class_name = "Unknown"
            try:
                text = ctrl.window_text().strip()
            except Exception:
                text = ""
            print(f"Rank {i}: Class: {class_name} | Text: {text}")

    # Check if there are enough controls.
    if len(controls) <= 262:
        print("Warning: Not enough controls to access rank 262.")
        return ""

    try:
        # Retrieve the text from the control at rank 262.
        headline_text = controls[262].window_text().strip()
    except Exception as e:
        print(f"Error retrieving text from rank 262: {e}")
        return ""

    # Apply the heuristic to extract only the first news item.
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
