"""
Monitors headlines on the "Breaking News - The Fly" page by dumping the entire HTML every 3 seconds
and parsing it with BeautifulSoup.

Steps:
1) Attaches to the correct tab in Chrome (which must be running with --remote-debugging-port=9222).
2) Every 3 seconds:
   - Evaluates document.documentElement.outerHTML
   - Parses the HTML with BeautifulSoup
   - Finds all <a class="newsTitleLink"> elements
   - Checks for new headlines
   - Writes them to a CSV file with timestamps
3) Emits a beep on Windows if an error occurs (and tries to recover).
4) Prints debug messages to the console.
"""

import pychrome
import time
import datetime
import csv

# For HTML parsing
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

    # If needed, you could be more specific and locate the table:
    # table = soup.select_one('.news_table.today.first_table')
    # if not table: ...
    # but let's just search the entire doc for a.newsTitleLink
    headline_links = soup.select('a.newsTitleLink')

    headlines = []
    for link in headline_links:
        text = link.get_text(strip=True)
        if text:
            headlines.append(text)
    return headlines

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

    seen_headlines = set()

    print("DEBUG: Beginning monitoring by dumping entire HTML every 3 seconds (Press Ctrl+C to stop).")

    try:
        while True:
            try:
                # Dump entire HTML
                html_text = dump_full_html(fly_tab)

                # Parse with BeautifulSoup
                headlines = parse_headlines_from_html(html_text)
                print(f"DEBUG: Found {len(headlines)} headlines in the HTML.")

                # Identify new items
                new_items = [h for h in headlines if h not in seen_headlines]

                if new_items:
                    # Append them to CSV with timestamps
                    with open(csv_filename, "a", newline="", encoding="utf-8") as csvfile:
                        writer = csv.writer(csvfile)
                        for headline in new_items:
                            seen_headlines.add(headline)
                            timestamp = datetime.datetime.now().isoformat()
                            writer.writerow([timestamp, headline])
                            print(f"DEBUG: New headline appended: {headline}")

                time.sleep(3)  # Sleep 3 seconds before next dump

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
