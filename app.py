#!/usr/bin/env python3

import requests
import re
import time
import subprocess
import os
import collections
import logging
import json



# --- Configuration ---
REDDIT_URL = "https://www.reddit.com/r/Tacticus_Codes/new.json"
NTFY_TOPIC_URL = "ntfy.sh/tacticus_codes" # User specified topic
CODES_FILE = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "notified_codes.txt"
)
LOG_FILE = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "code_scraper.txt"
)
USER_AGENT = "TacticusCodeBot/0.2 by RedditUserJoekki (Python Script)" # PLEASE UPDATE YourNameHere
FETCH_INTERVAL_SECONDS = 300  # 5 minutes
POST_LIMIT = 40  # Number of new posts to fetch each time, increased to account for flair filtering

# --- Reddit Flair Filtering ---
# Only posts with these flairs will be processed. Note the trailing space in the first one.
ALLOWED_FLAIRS = {"Codes + Referral ", "New Code"}

# --- Patterns ---
# Pattern for potential codes: 4-25 alphanumeric characters, often all caps.
# Will be converted to uppercase and then checked.
CANDIDATE_CODE_PATTERN = re.compile(r'\b[A-Z0-9]{3,25}\b')
# Pattern for referral codes (e.g., ABC-12-DEF or ABC-123-DEF)
REFERRAL_CODE_PATTERN = re.compile(r'^[A-Z]{3}-\d{2,3}-[A-Z]{3}$')

# --- Ignored Words (all uppercase) ---
# Common words, Reddit/game terms that are unlikely to be codes.
# This list is crucial and might need tuning.
IGNORED_WORDS_SET = {
    "NEW", "CODE", "CODES", "REFERRAL"
}

# Patterns for titles that suggest the code is in the post body
# (used if no direct code found in title). Case-insensitive search.
BODY_HINT_PATTERNS = [
    re.compile(r"^\s*(another|just a|one more|a new|some|more)\s+code\s*(!|\.|here|below|inside|for you)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*new\s+code\s*-\s*\d+.*blackstone.*", re.IGNORECASE), # e.g. "New Code - 100 Blackstone & 2000 Coin"
    re.compile(r"^\s*(the|latest|current|today'?s?)\s+code\s+is\s+(in|below|here|in the body|in post).*", re.IGNORECASE),
    re.compile(r"^\s*check\s+(the\s+)?(body|post|description|comments)\s+(for|for the)\s+code\s*$", re.IGNORECASE),
    re.compile(r"^\s*code\s+(in|inside)\s+(the\s+)?(post|body|description|comments)\s*(!|\.)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(new|latest|fresh|recent)\s+codes?\s*(!|\.)?\s*$", re.IGNORECASE), # For "NEW CODES!!" when codes are in body
    re.compile(r"^\s*found\s+a\s+(new\s+)?code\s*(!|\.)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*anyone\s+(got|have|know)\s+(a|any)\s+(new\s+)?code", re.IGNORECASE),
    re.compile(r"^\s*title\s*(says|has)\s*it\s*all\s*$", re.IGNORECASE), # If title is generic but implies content is key
    re.compile(r"^\s*look\s*inside\s*$", re.IGNORECASE)
]

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# --- Functions ---

def load_notified_codes(filename=CODES_FILE):
    """Loads already notified codes from a file."""
    if not os.path.exists(filename):
        return set()
    try:
        with open(filename, 'r') as f:
            return {line.strip().upper() for line in f if line.strip()}
    except IOError as e:
        logging.error(f"Error loading notified codes from {filename}: {e}")
        return set()

def save_notified_code(code, filename=CODES_FILE):
    """Appends a new code to the notified codes file."""
    try:
        with open(filename, 'a') as f:
            f.write(code.upper() + '\n')
        logging.info(f"Saved notified code: {code}")
    except IOError as e:
        logging.error(f"Error saving code {code} to {filename}: {e}")

def notify_ntfy(message, topic_url=NTFY_TOPIC_URL):
    """Sends a notification using requests to ntfy.sh."""
    try:
        if not topic_url.startswith(('http://', 'https://')):
            topic_url = f"https://{topic_url}"
        
        logging.info(f"Attempting to notify: {message} to {topic_url}")
        response = requests.post(topic_url, data=message.encode('utf-8'), headers={'Title': 'New Tacticus Code!'})
        
        subprocess.run(['/usr/bin/notify-send', "New Tacticus Code", message], check=True, capture_output=True)

        response.raise_for_status()
        logging.info(f"Successfully notified: {message} via ntfy.sh. Status: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send ntfy notification for '{message}': {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during ntfy notification for '{message}': {e}")
    return False

def extract_potential_codes_from_text(text):
    """Extracts potential codes from a given text string."""
    if not text:
        return []
    
    words = CANDIDATE_CODE_PATTERN.findall(text.upper())
    
    potential_codes = []
    for word in words:
        if REFERRAL_CODE_PATTERN.match(word):
            logging.debug(f"Ignoring referral code: {word}")
            continue
        if word in IGNORED_WORDS_SET:
            logging.debug(f"Ignoring common word: {word}")
            continue
        potential_codes.append(word)
    return potential_codes

def fetch_and_process_posts(notified_codes_set):
    """Fetches new posts from Reddit, processes them based on flair, and notifies new codes."""
    headers = {'User-Agent': USER_AGENT}
    params = {'limit': POST_LIMIT}
    
    logging.info(f"Fetching new posts from {REDDIT_URL}...")
    try:
        response = requests.get(REDDIT_URL, headers=headers, params=params, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching Reddit data: {e}")
        return notified_codes_set

    try:
        posts_data = response.json()
        if 'data' not in posts_data or 'children' not in posts_data['data']:
            logging.error("Reddit JSON data is not in the expected format.")
            return notified_codes_set
        posts = posts_data['data']['children']
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding Reddit JSON response: {e}")
        return notified_codes_set

    all_potential_codes_this_run = []
    processed_post_count = 0

    for post_entry in posts:
        if post_entry.get('kind') != 't3':
            continue
        post = post_entry.get('data', {})
        post_id = post.get('id', 'N/A')
        title = post.get('title', '')
        flair = post.get('link_flair_text') # Can be None

        # --- FLAIR FILTERING LOGIC ---
        if flair not in ALLOWED_FLAIRS:
            logging.debug(f"Skipping Post ID: {post_id} due to invalid flair: '{flair}'")
            continue

        #logging.info(f"Processing Post ID: {post_id} with flair '{flair}', Title: '{title[:50]}...'")
        processed_post_count += 1
        
        selftext = post.get('selftext', '')
        current_post_extracted_codes = []
        
        # 1. Try to extract codes directly from the title
        title_codes = extract_potential_codes_from_text(title)
        if title_codes:
            logging.debug(f"Codes found in title of post {post_id}: {title_codes}")
            current_post_extracted_codes.extend(title_codes)
        else:
            # 2. If no codes in title, check if title hints at code in body
            process_body = False
            for pattern in BODY_HINT_PATTERNS:
                if pattern.search(title):
                    logging.debug(f"Title of post {post_id} matches body hint pattern: {pattern.pattern}")
                    process_body = True
                    break
            
            if process_body:
                logging.debug(f"Extracting codes from selftext of post {post_id} due to title hint.")
                body_codes = extract_potential_codes_from_text(selftext)
                if body_codes:
                    logging.debug(f"Codes found in selftext of post {post_id}: {body_codes}")
                    current_post_extracted_codes.extend(body_codes)
                else:
                    logging.debug(f"No codes found in selftext of post {post_id} despite title hint.")
            else:
                logging.debug(f"No codes in title of post {post_id} and no strong hint to check body.")

        # Add unique codes found in this specific post to the list for frequency counting.
        for code in set(current_post_extracted_codes):
            all_potential_codes_this_run.append(code)

    logging.info(f"Processed {processed_post_count} posts with allowed flairs.")

    if not all_potential_codes_this_run:
        logging.info("No potential codes found in the processed posts.")
        return notified_codes_set

    code_counts = collections.Counter(all_potential_codes_this_run)
    logging.info(f"Potential code counts this run: {code_counts}")

    newly_confirmed_codes = []
    for code, count in code_counts.items():
        if count >= 2 and code not in notified_codes_set:
            logging.info(f"Confirmed new code: {code} (count: {count})")
            newly_confirmed_codes.append(code)
        elif code in notified_codes_set:
            logging.debug(f"Code {code} already notified.")
        elif count < 2:
            logging.debug(f"Code {code} appeared only {count} time(s), not enough for confirmation.")

    if newly_confirmed_codes:
        newly_confirmed_codes.sort()
        for code in newly_confirmed_codes:
            if notify_ntfy(code):
                save_notified_code(code)
                notified_codes_set.add(code)
            else:
                logging.warning(f"Notification failed for {code}. It will be re-attempted next run if still valid.")
    else:
        logging.info("No new codes to notify in this run.")
        
    return notified_codes_set

# --- Main Execution ---
if __name__ == "__main__":
    logging.info("Tacticus Code Scraper started.")
    logging.info(f"Filtering for flairs: {ALLOWED_FLAIRS}")
    
    try:
        with open(CODES_FILE, 'a'):
            pass
    except IOError as e:
        logging.critical(f"CRITICAL: Cannot create/access codes file {CODES_FILE}: {e}. Check permissions.")
        exit(1)

    current_notified_codes = load_notified_codes()
    logging.info(f"Loaded {len(current_notified_codes)} previously notified codes.")

    try:
        while True:
            current_notified_codes = fetch_and_process_posts(current_notified_codes)
            logging.info(f"Next check in {FETCH_INTERVAL_SECONDS} seconds.")
            time.sleep(FETCH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logging.info("Script interrupted by user. Exiting.")
    except Exception as e:
        logging.critical(f"An unhandled critical error occurred: {e}", exc_info=True)
    finally:
        logging.info("Tacticus Code Scraper stopped.")
