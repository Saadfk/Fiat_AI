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


def post_to_discord(channel_id, message):
    """
    Sends a message to a given Discord channel using the Bot API.
    Requires DISCORD_BOT_TOKEN.
    """
    url = f"https://discord.com/api/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"content": message}

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code not in (200, 201):
        print(f"ERROR posting to Discord: {response.status_code} {response.text}")


class MultiCSVHandler(FileSystemEventHandler):
    """
    A FileSystemEventHandler that tracks multiple CSV files for appended lines.
    For each file, we store how many bytes we've read so far.
    When a file is modified, we only read the newly added lines.
    """
    def __init__(self, csv_files):
        super().__init__()
        self.csv_files = csv_files

        # Track the file offsets so we only read truly new lines
        self.file_offsets = {}
        for f in csv_files:
            if os.path.exists(f):
                # Start from the end of the file so we don't re-process old lines
                self.file_offsets[f] = os.path.getsize(f)
            else:
                self.file_offsets[f] = 0

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
        Read only the new lines appended to file_name since last check.
        For each new line, we:
          1) Print it to console with an HH:MM timestamp
          2) Post it to Discord
        """
        current_offset = self.file_offsets[file_name]
        new_offset = os.path.getsize(file_name)

        if new_offset < current_offset:
            # File might have been truncated or rotated; reset
            current_offset = 0

        if new_offset > current_offset:
            # Read new lines
            with open(file_name, "r", encoding="utf-8") as f:
                f.seek(current_offset)
                new_data = f.read()
                self.file_offsets[file_name] = new_offset  # update offset

            lines = new_data.splitlines()
            for line in lines:
                if line.strip():
                    # Print to console with HH:MM timestamp
                    hhmm = datetime.datetime.now().strftime("%H:%M")
                    print(f"[{hhmm}] {file_name} -> {line}")

                    # Post to Discord
                    post_to_discord(
                        DISCORD_CHANNEL_ID,
                        f"**{file_name}** - {line}"
                    )


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
