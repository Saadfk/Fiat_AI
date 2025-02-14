import time
import winsound
import csv
import datetime
import logging
from pywinauto import Application, Desktop

###################################################################
# Configuration
###################################################################
POLL_INTERVAL = 0.5  # seconds between checks for feed updates
WINDOW_TITLE = "FIATFEED"  # Title of the window you're looking for

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
    Plays a short beep sound to indicate a news feed update.
    """
    winsound.Beep(550, 200)


def find_fiatfeed_pid():
    """
    Scans all top-level windows and returns the PID of the first window
    whose title contains the string in WINDOW_TITLE.
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
    Enumerates all controls in the 'window' and writes them to a CSV:
    Rank, ClassName, ControlText

    This helps you see which rank (index) each control has.
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
    Asks the user to enter a rank (0-based index) from the controls in the CSV,
    then returns the corresponding control. If the rank is invalid, tries again;
    if 'cancel', returns None.
    """
    controls = window.descendants()

    while True:
        rank_str = input("Enter the rank (index) of the control to monitor (or 'cancel' to exit): ").strip().lower()
        if rank_str == "cancel":
            return None

        try:
            rank = int(rank_str)
            if 0 <= rank < len(controls):
                control = controls[rank]
                log(f"Selected control rank {rank}.")

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

                log(f"Control info -> Class: {class_name}, Text: {text_preview[:300]}")

                confirm = input("Is this the correct control to monitor? (yes/no): ").strip().lower()
                if confirm == "yes":
                    log(f"User confirmed control rank {rank} for monitoring.")
                    return control
                else:
                    log(f"User rejected control rank {rank}.")
            else:
                log(f"Invalid rank: {rank_str}. Must be between 0 and {len(controls) - 1}.")
        except ValueError:
            log(f"Could not parse rank: {rank_str}. Please enter a valid integer.")


def monitor_control(control, main_window):
    """
    Continuously polls 'control' for text changes.
    If the text changes, beep and log it to fiatfeed_news.csv with a timestamp.

    Displays a simple spinner in the console instead of spamming logs
    for 'No change detected' every half second.
    """
    # We'll track a simple rotating spinner in the console.
    spinner = ['|', '/', '-', '\\']
    spinner_idx = 0

    try:
        last_text = control.window_text().strip()
    except Exception as e:
        log(f"Error retrieving initial text from control: {e}")
        last_text = ""

    log("Beginning to monitor this control for text changes...")

    while True:
        time.sleep(POLL_INTERVAL)

        # If the entire window is gone, let's stop.
        if not main_window.exists():
            log(f"{WINDOW_TITLE} window no longer exists. Monitoring loop will stop.")
            break

        # Try reading from the control
        try:
            current_text = control.window_text().strip()
        except Exception as e:
            log(f"Unable to read from control, probably gone: {e}")
            break

        if current_text != last_text:
            beep()
            log("Feed text changed!")
            log(f"Full updated text:\n{current_text}")

            # Log to CSV with the script's timestamp
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open("fiatfeed_news.csv", "a", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([stamp, current_text])

            last_text = current_text
        else:
            # Instead of logging "No change detected", we display a spinner
            print(f"Monitoring {spinner[spinner_idx]}", end='\r', flush=True)
            spinner_idx = (spinner_idx + 1) % len(spinner)


def monitor_fiatfeed_window():
    """
    Main routine:
      1) Attach to the FIATFEED window (by title).
      2) Dump controls to a debug CSV so you can see them.
      3) Prompt you for the rank of the control to monitor.
      4) Monitor that single control for changes (if any).
    """
    pid = find_fiatfeed_pid()
    if not pid:
        log(f"{WINDOW_TITLE} window not found. Exiting monitoring function.")
        return

    try:
        app = Application(backend="uia").connect(process=pid)
        main_window = app.window(title=WINDOW_TITLE)
        log(f"{WINDOW_TITLE} window attached successfully.")
    except Exception as e:
        log(f"Error attaching to {WINDOW_TITLE} window: {e}")
        return

    log("Waiting for the UI to populate completely...")
    time.sleep(2)

    dump_controls_to_csv(main_window, filename="all_controls_debug.csv")

    control = pick_control_by_rank(main_window)
    if not control:
        log("No control selected for monitoring. Exiting.")
        return

    monitor_control(control, main_window)


def main():
    """
    Keeps looking for the FIATFEED window every 5 seconds.
    If found, you can pick a control rank to monitor for text changes.
    """
    log(f"Starting {WINDOW_TITLE} auto-monitor. Waiting for {WINDOW_TITLE} window to appear...")

    while True:
        pid = find_fiatfeed_pid()
        if pid:
            log(f"{WINDOW_TITLE} window detected. Starting monitoring...")
            monitor_fiatfeed_window()
            log("Monitoring stopped. Will wait for window to reappear...")
        else:
            log(f"{WINDOW_TITLE} window not found. Retrying in 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    main()
