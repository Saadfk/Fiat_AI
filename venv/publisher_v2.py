import os
import time
import csv
import requests
import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import your bot token from Keys.py
from Keys import DISCORD_BOT_TOKEN

# ID of the Discord channel where you want to post new lines
DISCORD_CHANNEL_ID = 855359994547011604

# CSV files we want to watch (in the same directory as this script)
CSV_FILES_TO_WATCH = ["headlines.csv", "flylines.csv"]


def post_to_discord(channel_id, message=None, embed=None):
    """
    Sends a message to a given Discord channel using the Bot API.
    If an embed is provided, it sends the embed instead of plain text.
    """
    url = f"https://discord.com/api/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {}
    if embed:
        payload["embeds"] = [embed]
    else:
        payload["content"] = message

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code not in (200, 201):
        print(f"ERROR posting to Discord: {response.status_code} {response.text}")


class MultiCSVHandler(FileSystemEventHandler):
    """
    A FileSystemEventHandler that tracks multiple CSV files for appended lines.
    For each file, we store:
      - the last file offset so that only truly new lines are processed
      - a set of lines already posted to avoid duplicates
    """

    def __init__(self, csv_files):
        super().__init__()
        self.csv_files = csv_files

        # Track the file offsets so we only read truly new lines
        self.file_offsets = {}
        # Track lines that have already been posted to avoid duplicates
        self.posted_lines = {}
        for f in csv_files:
            if os.path.exists(f):
                self.file_offsets[f] = os.path.getsize(f)
            else:
                self.file_offsets[f] = 0
            self.posted_lines[f] = set()

    def on_modified(self, event):
        """
        Called by watchdog whenever a file in the watched directory is modified.
        We only care if it's one of our CSV files.
        """
        file_path = os.path.abspath(event.src_path)
        file_name = os.path.basename(file_path)

        if file_name in self.csv_files:
            self.process_new_lines(file_name)

    def process_new_lines(self, file_name):
        """
        Read only the new lines appended to file_name since the last check.
        For each new line, if it hasn’t been posted before:
          1) Print it to console with an HH:MM timestamp
          2) Post it to Discord using an embed that includes:
             - A title: "RTRS" (orange) for headlines.csv or "FLY" (blue) for flylines.csv
             - The current time (hh:mm format) and the new line as the description
        """
        current_offset = self.file_offsets[file_name]
        new_offset = os.path.getsize(file_name)

        if new_offset < current_offset:
            # File might have been truncated or rotated; reset and clear duplicates
            current_offset = 0
            self.posted_lines[file_name].clear()

        if new_offset > current_offset:
            # Read new lines
            with open(file_name, "r", encoding="utf-8") as f:
                f.seek(current_offset)
                new_data = f.read()
                self.file_offsets[file_name] = new_offset  # update offset

            lines = new_data.splitlines()
            for line in lines:
                if line.strip():
                    # Check for duplicate lines before posting
                    if line in self.posted_lines[file_name]:
                        continue  # Skip duplicate
                    self.posted_lines[file_name].add(line)

                    # Get current timestamp in hh:mm format
                    hhmm = datetime.datetime.now().strftime("%H:%M")

                    # Set embed title and color based on the CSV file name
                    if file_name == "headlines.csv":
                        title = "RTRS"
                        color = 16753920  # Orange (hex: FFA500)
                    elif file_name == "flylines.csv":
                        title = "FLY"
                        color = 255  # Blue (hex: 0000FF)
                    else:
                        title = file_name
                        color = 0

                    # Create an embed payload with the timestamp and line content
                    embed = {
                        "title": title,
                        "description": f"[{hhmm}] {line}",
                        "color": color
                    }

                    # Print to console
                    print(f"[{hhmm}] {file_name} -> {line}")
                    # Post to Discord using embed
                    post_to_discord(DISCORD_CHANNEL_ID, embed=embed)


def main():
    # Determine the directory to watch: same as this script
    watch_dir = os.path.dirname(os.path.abspath(__file__))

    # Create our event handler for multiple CSVs
    event_handler = MultiCSVHandler(CSV_FILES_TO_WATCH)

    # Create and start the observer
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=False)
    observer.start()

    print("Monitoring CSV changes in:", watch_dir)
    print("Watching files:", CSV_FILES_TO_WATCH)
    print("(Press Ctrl+C to stop)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping observer...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
