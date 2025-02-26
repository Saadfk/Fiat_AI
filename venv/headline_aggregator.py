import time

class HeadlineAggregator:
    """
    Collects lines (headlines) for a short time window before flushing them as a single tweet.
    """
    def __init__(self, flush_interval=5):
        """
        :param flush_interval: how many seconds to wait after the *last* added line
                               before flushing them into one combined tweet.
        """
        self.flush_interval = flush_interval
        self.buffer = []
        self.last_line_time = 0

    def add_line(self, line):
        """
        Add a single headline line to the buffer and update the timestamp.
        """
        now = time.time()
        self.buffer.append(line)
        self.last_line_time = now

    def should_flush(self):
        """
        Check if it's been > flush_interval seconds since the last added line.
        If we have no lines, returns False.
        """
        if not self.buffer:
            return False
        now = time.time()
        return (now - self.last_line_time) > self.flush_interval

    def flush(self):
        """
        Returns the combined text of all buffered lines and clears the buffer.
        """
        combined = "\n".join(self.buffer)
        self.buffer.clear()
        return combined
