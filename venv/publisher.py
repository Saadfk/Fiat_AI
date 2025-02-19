import discord
import requests
from Keys import DISCORD_BOT_TOKEN, NOTEBOOK_CHANNEL_ID, Linkedin_Access_Token, LINKEDIN_AUTHOR_URN, \
    TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET

# Additional Discord Channel IDs
ADDITIONAL_CHANNEL_ID_1 = 1323659231064490044
TARGET_CHANNEL_ID = 855359994547011604
ADDITIONAL_CHANNEL_ID_2 = 1341449447653118059


def split_into_chunks(content, chunk_size=280):
    words = content.split()
    chunks = []
    current_chunk = ""

    for word in words:
        if len(current_chunk) + len(word) + 1 <= chunk_size:  # +1 for the space
            current_chunk += (word + " ")
        else:
            chunks.append(current_chunk.strip())
            current_chunk = word + " "
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks


import requests
from requests_oauthlib import OAuth1
import Keys

def post_to_twitter(content):
    url = "https://api.twitter.com/2/tweets"

    # OAuth1 Authentication
    auth = OAuth1(
        Keys.TWITTER_CONSUMER_KEY,
        Keys.TWITTER_CONSUMER_SECRET,
        Keys.TWITTER_ACCESS_TOKEN,
        Keys.TWITTER_ACCESS_SECRET,
    )

    # Post content directly (no splitting)
    payload = {"text": content}

    response = requests.post(url, auth=auth, json=payload)
    if response.status_code == 201:
        tweet_id = response.json().get("data", {}).get("id")
        print(f"Posted tweet: {content}")
        return tweet_id
    else:
        print(f"Failed to post to Twitter: {response.text}")
        return None


def post_to_linkedin(content):
    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {Linkedin_Access_Token}",
        "Content-Type": "application/json"
    }
    payload = {
        "author": LINKEDIN_AUTHOR_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": content
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 201:
        print("Posted to LinkedIn successfully!")
    else:
        print(f"Failed to post to LinkedIn: {response.text}")


class DiscordClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f"Logged in as {self.user}")

    async def on_message(self, message):
        if message.channel.id in [int(NOTEBOOK_CHANNEL_ID), ADDITIONAL_CHANNEL_ID_1, ADDITIONAL_CHANNEL_ID_2]:
            content = message.content
            print(f"New message in channel {message.channel.id}: {content}")

            # Repost to TARGET_CHANNEL_ID
            target_channel = self.get_channel(TARGET_CHANNEL_ID)
            if target_channel:
                await target_channel.send(content)
            if message.channel.id == int(NOTEBOOK_CHANNEL_ID):
                # Post to LinkedIn
                post_to_linkedin(content)

                # Post to Twitter
                post_to_twitter(content)


if __name__ == "__main__":
    client = DiscordClient()
    client.run(DISCORD_BOT_TOKEN)
