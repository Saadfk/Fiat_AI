import os
import time
import csv
import requests
import datetime
import re

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Discord
from Keys import DISCORD_BOT_TOKEN
DISCORD_CHANNEL_ID = 855359994547011604

# CSV files we want to watch
CSV_FILES_TO_WATCH = ["headlines.csv", "flylines.csv"]

#################### NEW IMPORTS ####################
from usage_tracker import UsageTracker
from headline_aggregator import HeadlineAggregator

# Suppose you have a publisher.py with your post_to_twitter function
from publisher import post_to_twitter
# from publisher import post_to_linkedin  # if needed

# Create a usage tracker: 100 tweets in 24h
twitter_usage = UsageTracker(
    usage_file="tweet_usage.json",
    max_attempts=100,
    time_window=24*3600
)

# Create a single aggregator for all lines (or you could do one per file if you prefer)
aggregator = HeadlineAggregator(flush_interval=5)


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
    """

    def __init__(self, csv_files):
        super().__init__()
        self.csv_files = csv_files

        # Track the file offsets so we only read truly new lines
        self.file_offsets = {}
        # Track cleaned lines that have already been posted to avoid duplicates
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
        For each new line that hasn't been posted before:
          1) Remove any embedded timestamp
          2) For fly news, remove the "Fly " prefix if present
          3) Add it to the aggregator (instead of immediately tweeting)
          4) Post to Discord as usual (one by one) or you could aggregate that too
        """
        current_offset = self.file_offsets[file_name]
        new_offset = os.path.getsize(file_name)

        # Handle file truncation
        if new_offset < current_offset:
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
                    # Remove leading timestamp
                    pattern = r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?,\s*'
                    cleaned_line = re.sub(pattern, '', line).strip()

                    # Remove "Fly " prefix if in flylines.csv
                    if file_name == "flylines.csv" and cleaned_line.startswith("Fly "):
                        cleaned_line = cleaned_line[len("Fly "):].strip()

                    # Check for duplicates
                    if cleaned_line in self.posted_lines[file_name]:
                        continue
                    self.posted_lines[file_name].add(cleaned_line)

                    # Add to aggregator
                    aggregator.add_line(f"{file_name.upper()}: {cleaned_line}")

                    # Also post to Discord individually (or you can aggregate):
                    hhmm = datetime.datetime.now().strftime("%H:%M")
                    if file_name == "headlines.csv":
                        title = "RTRS"
                        color = 16753920  # Orange
                    elif file_name == "flylines.csv":
                        title = "FLY"
                        color = 255       # Blue
                    else:
                        title = file_name
                        color = 0

                    embed = {
                        "title": title,
                        "description": f"[{hhmm}] {cleaned_line}",
                        "color": color
                    }
                    post_to_discord(DISCORD_CHANNEL_ID, embed=embed)

                    # Print to console
                    print(f"[{hhmm}] {file_name} -> {cleaned_line}")


def main():
    watch_dir = os.path.dirname(os.path.abspath(__file__))
    event_handler = MultiCSVHandler(CSV_FILES_TO_WATCH)

    from watchdog.observers import Observer
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=False)
    observer.start()

    print("Monitoring CSV changes in:", watch_dir)
    print("Watching files:", CSV_FILES_TO_WATCH)
    print("(Press Ctrl+C to stop)")

    try:
        while True:
            time.sleep(1)
            # Check if aggregator is ready to flush
            if aggregator.should_flush():
                # Combine lines into one message
                combined_message = aggregator.flush()

                # If we exceed tweet length, you may want to chunk it,
                # but here's a simple approach:
                if len(combined_message) > 280:
                    # Quick demonstration: trim or handle in multiple tweets
                    combined_message = combined_message[:280] + "..."

                # Check usage limit
                if twitter_usage.can_post():
                    twitter_usage.record_post()
                    # Actually post the aggregated tweet
                    hhmm = datetime.datetime.now().strftime("%H:%M")
                    post_to_twitter(f"[{hhmm} Aggregated]\n{combined_message}")
                else:
                    print("SKIPPED TWEET (limit reached for today).")
    except KeyboardInterrupt:
        print("Stopping observer...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
