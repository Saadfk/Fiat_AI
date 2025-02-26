import os
import json
import time
from collections import deque


class UsageTracker:
    """
    Tracks tweet-post attempts in a rolling 24-hour window (or any time_window).
    Persists usage in a JSON file so it survives restarts.
    """

    def __init__(self, usage_file="tweet_usage.json", max_attempts=100, time_window=24 * 3600):
        """
        :param usage_file: Path to a JSON file where we store timestamps of tweet attempts.
        :param max_attempts: Max allowed attempts in the time window (default=100).
        :param time_window: Rolling time window in seconds (default=24h).
        """
        self.usage_file = usage_file
        self.max_attempts = max_attempts
        self.time_window = time_window
        self.attempts = deque()  # will store timestamps (float)

        # Load existing usage from file
        self.load_usage()
        # Prune any old timestamps right away
        self.prune()

    def load_usage(self):
        """Load existing usage timestamps from the JSON file."""
        if os.path.exists(self.usage_file):
            with open(self.usage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # data is a list of timestamps
                self.attempts = deque(data)
        else:
            self.attempts = deque()

    def save_usage(self):
        """Save current usage timestamps to the JSON file."""
        with open(self.usage_file, "w", encoding="utf-8") as f:
            json.dump(list(self.attempts), f)

    def prune(self):
        """Remove timestamps older than time_window from the front of the deque."""
        now = time.time()
        while self.attempts and (now - self.attempts[0]) > self.time_window:
            self.attempts.popleft()

    def can_post(self):
        """
        Check if we're still under the max_attempts limit in the rolling window.
        Returns True if we can post, False if we've hit the limit.
        """
        self.prune()
        return len(self.attempts) < self.max_attempts

    def record_post(self):
        """Record a new tweet attempt timestamp and save to file."""
        now = time.time()
        self.attempts.append(now)
        self.save_usage()
