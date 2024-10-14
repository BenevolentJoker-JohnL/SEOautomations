import os
import time
import re
import logging
import praw
from flask import Flask, request, redirect
from googleapiclient.discovery import build
from colorama import Fore, init
from dotenv import load_dotenv
from threading import Thread

# Initialize colorama and logging
init(autoreset=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Display donation addresses once when the app starts
def display_donation_addresses():
    logging.info("Displaying donation addresses...")
    print(Fore.RED + "Welcome to Dominion SEO Crossbridge created by The Joker for Miniverse + Seniorage Circus: Pyreswap. If you would like to support the original creator of this script, you may send donations via crypto to the following addresses:")
    donation_addresses = {
        "BTC": "3NuS3dgmAW47pRE3aPYMXFMjaAVKtLgoFd",
        "ETH": "0x56FEf6ddC7E25522C4dfE6CC",
        "Algorand": "F1C012308Bf272A8NTXDMG5P7SXLV7K4UGFAMEKMMKAESB7WQ6FZTH7OBCPVQ6QNST42ERJC4Q",
        "DOT": "15EpN9zvf6wyPYnDqSm3pwxYB55iUGNqzk9GAad796f78rJY",
        "LTC": "MEoXG3HSRGUZf67U4dHkNyTjwKpmGBC5RJ"
    }
    for currency, address in donation_addresses.items():
        print(Fore.YELLOW + f"{currency}: {address}")

# Load environment variables from .env file
load_dotenv()

# API keys from environment
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
CHANNEL_ID = os.getenv("CHANNEL_ID")
SUBREDDIT_NAME = os.getenv("SUBREDDIT_NAME")

# Validate environment variables
if not all([YOUTUBE_API_KEY, CHANNEL_ID, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, SUBREDDIT_NAME]):
    logging.error("One or more environment variables are not properly set. Please check your .env file.")
    exit(1)

# YouTube API client
try:
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    logging.info("YouTube API client initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing YouTube API client: {e}")
    exit(1)

# Flask app for Reddit OAuth
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Reddit API setup using PRAW
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    redirect_uri='http://localhost:7865/callback',
    user_agent=REDDIT_USER_AGENT
)

@app.route('/')
def home():
    try:
        # Redirect to Reddit's OAuth page to ask for permissions
        authorization_url = reddit.auth.url(scopes=["identity", "submit"], state="random_state", duration="permanent")
        return redirect(authorization_url)
    except Exception as e:
        logging.error(f"Error during Reddit authentication: {e}")
        return "An error occurred while trying to authenticate with Reddit.", 500

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        logging.error("Authorization code not found in callback.")
        return "Authorization code not found.", 400

    try:
        # Complete OAuth flow
        reddit.auth.authorize(code)
        user = reddit.user.me()
        logging.info(f"Authenticated as Reddit user: {user.name}")
        return f"Authenticated as: {user.name}"
    except Exception as e:
        logging.error(f"Error during OAuth callback: {e}")
        return "An error occurred during the Reddit OAuth process.", 500

# Function to check for new YouTube livestreams
def check_new_livestream(channel_id, last_video_id=None):
    try:
        request = youtube.search().list(
            part='snippet',
            channelId=channel_id,
            eventType='live',
            type='video',
            maxResults=1,
            order='date'
        )
        response = request.execute()
        if response.get('items'):
            latest_video = response['items'][0]
            video_id = latest_video['id']['videoId']
            video_title = latest_video['snippet']['title']
            video_link = f"https://www.youtube.com/watch?v={video_id}"

            if video_id != last_video_id:
                logging.info(f"New live stream detected: {video_title}")
                return video_id, video_title, video_link
        return None, None, None
    except Exception as e:
        logging.error(f"Error fetching data from YouTube API: {e}")
        return None, None, None

# Function to format the announcement message
def format_announcement(video_title):
    episode_match = re.search(r'Episode\s*(\d+):\s*(.*)', video_title, re.IGNORECASE)
    if episode_match:
        episode_number = episode_match.group(1)
        episode_title = episode_match.group(2)
        announcement = f"LIVE NOW! PYRESWAP SHOW Episode {episode_number}: {episode_title}"
    else:
        announcement = f"LIVE NOW! PYRESWAP SHOW: {video_title}"
    return announcement

# Cross-posting function to Reddit with thumbnail
def cross_post_to_reddit(live_title, live_link, video_thumbnail_url):
    announcement = format_announcement(live_title)
    full_message = f"{announcement}\nWatch here: {live_link}"

    try:
        subreddit = reddit.subreddit(SUBREDDIT_NAME)
        post_title = f"New Pyreswap Show Episode: {announcement}"

        # Submitting a link post instead of a selftext post
        subreddit.submit(title=post_title, url=live_link)

        logging.info("Successfully posted to Reddit as a link post with video thumbnail.")
    except Exception as e:
        logging.error(f"Error posting to Reddit: {e}")

# Function to check for new YouTube livestreams and fetch thumbnail
def check_new_livestream(channel_id, last_video_id=None):
    try:
        request = youtube.search().list(
            part='snippet',
            channelId=channel_id,
            eventType='live',
            type='video',
            maxResults=1,
            order='date'
        )
        response = request.execute()
        if response.get('items'):
            latest_video = response['items'][0]
            video_id = latest_video['id']['videoId']
            video_title = latest_video['snippet']['title']
            video_link = f"https://www.youtube.com/watch?v={video_id}"
            video_thumbnail_url = latest_video['snippet']['thumbnails']['high']['url']

            if video_id != last_video_id:
                logging.info(f"New live stream detected: {video_title}")
                return video_id, video_title, video_link, video_thumbnail_url
        return None, None, None, None
    except Exception as e:
        logging.error(f"Error fetching data from YouTube API: {e}")
        return None, None, None, None

# Monitor YouTube and post to Reddit
def monitor_and_post(channel_id, sleep_interval=300):
    last_video_id = None
    live_stream_detected = False
    suspension_duration = 16 * 60 * 60  #adjust as needed

    while True:
        logging.info(f"Checking for new live streams on YouTube channel: {channel_id}...")

        if live_stream_detected:
            logging.info("Live stream detected previously, suspending cross-posting for 4 hours.")
            time.sleep(suspension_duration)
            live_stream_detected = False
            continue

        video_id, video_title, video_link, video_thumbnail_url = check_new_livestream(channel_id, last_video_id)

        if video_id:
            last_video_id = video_id
            live_stream_detected = True
            cross_post_to_reddit(video_title, video_link, video_thumbnail_url)

        logging.info(f"Sleeping for {sleep_interval} seconds before next check.")
        time.sleep(sleep_interval)


# Start monitoring YouTube live streams
def start_monitoring():
    display_donation_addresses()
    monitor_and_post(CHANNEL_ID)

if __name__ == '__main__':
    flask_thread = Thread(target=lambda: app.run(port=7865))
    flask_thread.start()
    start_monitoring()
