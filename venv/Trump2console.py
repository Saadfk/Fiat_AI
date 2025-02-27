import feedparser
import time

RSS_FEED_URL = 'https://trumpstruth.org/feed'

def fetch_feed():
    return feedparser.parse(RSS_FEED_URL)

def main():
    seen = set()
    while True:
        feed = fetch_feed()
        for entry in feed.entries:
            if entry.id not in seen:
                print(f"{entry.published}: {entry.title}\n{entry.link}\n")
                seen.add(entry.id)
        time.sleep(1)  # Poll every 10 seconds; adjust as needed

if __name__ == '__main__':
    main()
