import praw
import pandas as pd
import datetime as dt
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from zoneinfo import ZoneInfo  # For timezone conversion (Python 3.9+)

# Initialize the VADER sentiment analyzer
analyzer = SentimentIntensityAnalyzer()


def unix_to_date(ts):
    """Convert a Unix timestamp to a date string (YYYY-MM-DD)."""
    return dt.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')


def main():
    # Set up your Reddit API credentials here
    reddit = praw.Reddit(
        client_id="CdcO13z12ftLbFGbW9SGXQ",  # Replace with your client ID
        client_secret="4GSmVJ4Cd6syPfjdu5ZVXc2QxCZ5qA",  # Replace with your client secret
        user_agent="script:reddit_sentiment:v1.0 (by /u/Competitive_Corgi_12)"  # Replace with your Reddit username
    )

    subreddit = reddit.subreddit('wallstreetbets')
    data_list = []

    # Define time window: last 7 days (UTC)
    now = dt.datetime.utcnow()
    start_time = now - dt.timedelta(days=7)

    print("Fetching posts from the last 7 days...")
    # Fetch submissions (posts)
    for submission in subreddit.new(limit=1000):
        created = dt.datetime.utcfromtimestamp(submission.created_utc)
        if created < start_time:
            continue  # Skip posts older than 7 days
        # Use the post's score as the weight (minimum weight of 1)
        weight = submission.score if submission.score > 0 else 1
        # Combine title and selftext for sentiment analysis
        combined_text = submission.title + " " + (submission.selftext or "")
        sentiment = analyzer.polarity_scores(combined_text)['compound']
        data_list.append({
            'datetime': created,
            'sentiment': sentiment,
            'weight': weight,
            'type': 'post'
        })

    print("Fetching comments from the last 7 days...")
    # Fetch comments
    for comment in subreddit.comments(limit=1000):
        created = dt.datetime.utcfromtimestamp(comment.created_utc)
        if created < start_time:
            continue  # Skip comments older than 7 days
        weight = comment.score if comment.score > 0 else 1
        sentiment = analyzer.polarity_scores(comment.body)['compound']
        data_list.append({
            'datetime': created,
            'sentiment': sentiment,
            'weight': weight,
            'type': 'comment'
        })

    if not data_list:
        print("No data fetched. Exiting script.")
        return

    # Create DataFrame from the collected data
    df = pd.DataFrame(data_list)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df.set_index('datetime', inplace=True)
    # Localize as UTC and convert to Casablanca time
    df.index = df.index.tz_localize('UTC').tz_convert('Africa/Casablanca')

    # Define function to compute weighted average sentiment in a group
    def weighted_avg(group):
        return (group['sentiment'] * group['weight']).sum() / group['weight'].sum()

    # Resample into 12‑hour intervals and compute the weighted average sentiment
    weighted_sentiment_12h = df.resample('12H').apply(weighted_avg).reset_index(name='weighted_sentiment')

    # Set up Casablanca time formatting for the x-axis
    casablanca_tz = ZoneInfo("Africa/Casablanca")
    date_format = mdates.DateFormatter("%Y-%m-%d %H:%M", tz=casablanca_tz)

    # Plotting
    plt.figure(figsize=(12, 6))

    # Plot weighted sentiment as a blue line with circle markers
    plt.plot(weighted_sentiment_12h['datetime'],
             weighted_sentiment_12h['weighted_sentiment'],
             marker='o', linestyle='-', label="Weighted Sentiment", color='blue')

    # Fill the area below 0 in red when sentiment is negative
    plt.fill_between(weighted_sentiment_12h['datetime'],
                     weighted_sentiment_12h['weighted_sentiment'],
                     0,
                     where=(weighted_sentiment_12h['weighted_sentiment'] < 0),
                     interpolate=True,
                     color='red', alpha=0.3)

    # Draw a horizontal dashed line at y=0
    plt.axhline(0, color='black', linestyle='--', linewidth=1)

    # Highlight the most recent data point in orange
    last_point = weighted_sentiment_12h.iloc[-1]
    plt.scatter(last_point['datetime'], last_point['weighted_sentiment'],
                color='orange', s=100, zorder=5, label="Most Recent")

    # Titles and labels
    plt.title("12-Hour Weighted Sentiment Scores (Last 7 Days) for r/WSB", fontsize=14)
    plt.xlabel("Datetime (Africa/Casablanca)", fontsize=12)
    plt.ylabel("Weighted Average Sentiment Score (Compound)", fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.5)

    # Format x-axis to show Casablanca times clearly
    ax = plt.gca()
    ax.xaxis.set_major_formatter(date_format)
    plt.xticks(rotation=45, fontsize=10)
    plt.yticks(fontsize=10)

    plt.legend(fontsize=10)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()