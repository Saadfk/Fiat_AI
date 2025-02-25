"""
Monitors headlines on the "Breaking News - The Fly" page by forcibly reloading
the page every 3 seconds, then parsing the entire HTML with BeautifulSoup.

Steps:
1) Attaches to the correct tab in Chrome (which must be running with --remote-debugging-port=9222).
2) Loads existing headlines from flylines.csv so we never re-publish duplicates.
3) Every 3 seconds:
   - Calls Page.reload to refresh the page
   - Waits 2 seconds for the page to load
   - Evaluates document.documentElement.outerHTML
   - Parses the HTML with BeautifulSoup
   - Finds all <a class="newsTitleLink"> elements
   - Checks for new headlines
   - Writes them to flylines.csv with timestamps
4) Emits a beep on Windows if an error occurs (and tries to recover).
5) Prints debug messages to the console, including a short HH:MM timestamp for new headlines.
"""

import os
import pychrome
import time
import datetime
import csv

from bs4 import BeautifulSoup

# For Windows beep
try:
    import winsound
    HAVE_WINSOUND = True
except ImportError:
    HAVE_WINSOUND = False


def beep_error():
    """Emit a triple beep sequence on Windows to alert of an error."""
    if not HAVE_WINSOUND:
        print("ERROR: winsound not available on this platform. Cannot beep.")
        return
    for _ in range(3):
        winsound.Beep(1000, 500)  # frequency=1000 Hz, duration=500 ms
        time.sleep(0.1)


def attach_to_fly_tab(browser, target_title="Breaking News - The Fly"):
    """
    Searches through all tabs, briefly attaching to each to check document.title.
    If we find the correct one, we stay attached and do NOT stop() it.
    Raises RuntimeError if not found.
    """
    tabs = browser.list_tab()
    print(f"DEBUG: Found {len(tabs)} tabs in this Chrome instance.")

    for t in tabs:
        try:
            t.start()
            t.call_method("Runtime.enable")
            # Check the page title
            result = t.call_method("Runtime.evaluate", expression="document.title")
            doc_title = result.get("result", {}).get("value", "")
            print(f"DEBUG: Tab ID={t.id}, Title={doc_title}")

            if target_title in doc_title:
                print("DEBUG: Found the correct tab. Staying attached.")
                return t  # We do NOT call t.stop() here, so we remain attached.

            # Not the correct tab, so detach
            t.stop()

        except Exception as e:
            print(f"DEBUG: Error checking tab ID={t.id} -> {e}")
            try:
                t.stop()
            except:
                pass

    raise RuntimeError(f"Could not locate a tab titled '{target_title}'")


def refresh_page(tab):
    # print("DEBUG: Refreshing the page...")
    # Pass arguments as keyword args, not a dict
    tab.call_method("Page.reload", ignoreCache=True)
    time.sleep(4)  # Wait a bit for the page to reload



def dump_full_html(tab):
    """
    Uses pychrome to evaluate document.documentElement.outerHTML
    and returns the entire HTML as a string.
    """
    js_code = "document.documentElement.outerHTML"
    result = tab.call_method("Runtime.evaluate", expression=js_code)
    html_content = result.get("result", {}).get("value", "")
    return html_content


def parse_headlines_from_html(html_text):
    """
    Given a string of HTML, parse it with BeautifulSoup and return
    a list of headlines found in <a class="newsTitleLink">.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    headline_links = soup.select('a.newsTitleLink')
    headlines = []
    for link in headline_links:
        text = link.get_text(strip=True)
        if text:
            headlines.append(text)
    return headlines


def load_existing_headlines(csv_filename):
    """
    Reads the CSV file if it exists, and returns a set of all headlines
    previously stored. This ensures we don't re-publish duplicates across runs.
    """
    existing = set()
    if os.path.exists(csv_filename):
        with open(csv_filename, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    # Each row is [timestamp, headline]
                    headline = row[1]
                    existing.add(headline)
    return existing


def main():
    csv_filename = "flylines.csv"

    print("DEBUG: Connecting to Chrome on port 9222...")
    browser = pychrome.Browser(url="http://127.0.0.1:9222")

    # Attach to the tab
    try:
        fly_tab = attach_to_fly_tab(browser, "Breaking News - The Fly")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        beep_error()
        return

    # Load existing headlines so we don't publish duplicates across runs
    seen_headlines = load_existing_headlines(csv_filename)
    print(f"DEBUG: Loaded {len(seen_headlines)} existing headlines from {csv_filename}.")

    print("DEBUG: Beginning monitoring by reloading page every 3 seconds (Press Ctrl+C to stop).")

    try:
        while True:
            try:
                # 1) Refresh the page
                refresh_page(fly_tab)

                # 2) Dump entire HTML
                html_text = dump_full_html(fly_tab)

                # 3) Parse with BeautifulSoup
                headlines = parse_headlines_from_html(html_text)
                #print(f"DEBUG: Found {len(headlines)} headlines in the HTML.")

                # 4) Identify new items
                new_items = [h for h in headlines if h not in seen_headlines]

                if new_items:
                    with open(csv_filename, "a", newline="", encoding="utf-8") as csvfile:
                        writer = csv.writer(csvfile)
                        for headline in new_items:
                            seen_headlines.add(headline)
                            timestamp = datetime.datetime.now().isoformat()

                            # Print to console with a short HH:MM stamp
                            hhmm = datetime.datetime.now().strftime("%H:%M")
                            print(f"[{hhmm}] New headline -> {headline}")

                            # Write to CSV
                            writer.writerow([timestamp, headline])

                # 5) Wait 1 more second to make a total of ~3 seconds cycle
                time.sleep(1)

            except pychrome.exceptions.RuntimeException as re:
                print(f"ERROR: RuntimeException occurred: {re}")
                beep_error()
                # Attempt to re-locate & re-attach
                time.sleep(5)
                try:
                    fly_tab = attach_to_fly_tab(browser, "Breaking News - The Fly")
                except RuntimeError as e:
                    print(f"ERROR: {e}")
                    beep_error()
                    continue  # keep retrying

            except Exception as e:
                print(f"ERROR: Unexpected exception: {e}")
                beep_error()
                time.sleep(5)

    except KeyboardInterrupt:
        print("Monitoring stopped by user (KeyboardInterrupt).")
    finally:
        # Cleanly stop the tab session
        try:
            print("DEBUG: Stopping the tab session and exiting...")
            fly_tab.stop()
        except:
            pass


if __name__ == "__main__":
    main()
