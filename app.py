#!/usr/bin/env python3

import praw
import requests
import re
import time
import subprocess
import os
import collections
import logging
import json



# --- Configuration Loading Function ---
def load_config(config_path="config.json"):
    """Load configuration from JSON file."""
    try:
        config_file_path = os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
            config_path
        )
        
        with open(config_file_path, 'r') as f:
            config = json.load(f)
            
        # Validate required sections
        required_sections = ['reddit', 'application', 'notifications', 'filtering', 'patterns']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")
                
        return config
        
    except FileNotFoundError:
        print(f"CRITICAL: Configuration file not found: {config_path}")
        print("Please create a config.json file with the required settings.")
        raise
    except json.JSONDecodeError as e:
        print(f"CRITICAL: Invalid JSON in configuration file: {e}")
        raise
    except Exception as e:
        print(f"CRITICAL: Error loading configuration: {e}")
        raise

# --- Initial Logging Setup (basic console logging) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Start with console only
)

# --- Load Configuration ---
config = load_config()
logging.info("Configuration loaded successfully")

# --- Configuration Variables ---
# Reddit API Configuration
REDDIT_CLIENT_ID = config['reddit']['client_id']
REDDIT_CLIENT_SECRET = config['reddit']['client_secret']
SUBREDDITS_CONFIG = config['reddit']['subreddits']
USER_AGENT = config['reddit']['user_agent']

# Application Configuration
FETCH_INTERVAL_SECONDS = config['application']['fetch_interval_seconds']
POST_LIMIT = config['application']['post_limit']

# File paths
CODES_FILE = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    config['application']['codes_file']
)
LOG_FILE = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    config['application']['log_file']
)

# Notification Configuration
NTFY_TOPIC_URL = config['notifications']['ntfy_topic_url']

# --- Filtering Configuration ---
TRUSTED_USERS = set(config['filtering']['trusted_users'])

# --- Patterns ---
CANDIDATE_CODE_PATTERN = re.compile(config['patterns']['candidate_code_pattern'])
REFERRAL_CODE_PATTERN = re.compile(config['patterns']['referral_code_pattern'])

# --- Ignored Words ---
IGNORED_WORDS_SET = set(config['filtering']['ignored_words'])

# --- Proper Logging Setup (with file logging) ---
# Clear existing handlers and set up new ones with the loaded config
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

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
        
        #subprocess.run(['/usr/bin/notify-send', "New Tacticus Code", message], check=True, capture_output=True)

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

def initialize_reddit_client():
    """Initialize and return a Reddit client using PRAW."""
    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=USER_AGENT,
            read_only=True  # We only need read access
        )
        # Test the connection
        reddit.auth.limits
        logging.info("Reddit API client initialized successfully")
        return reddit
    except Exception as e:
        logging.error(f"Failed to initialize Reddit client: {e}")
        return None

def fetch_and_process_posts_praw(notified_codes_set):
    """Fetches new posts from multiple subreddits using PRAW API."""
    reddit = initialize_reddit_client()
    if reddit is None:
        logging.error("Cannot initialize Reddit client")
        return None
    
    all_posts = []
    subreddit_names = list(SUBREDDITS_CONFIG.keys())
    logging.info(f"Fetching new posts from r/{'+'.join(subreddit_names)} using Reddit API...")
    
    try:
        # Create a multireddit by joining subreddit names with '+'
        multireddit_name = '+'.join(subreddit_names)
        multireddit = reddit.subreddit(multireddit_name)
        
        # Fetch new posts with the specified limit
        posts = list(multireddit.new(limit=POST_LIMIT))
        logging.info(f"Successfully fetched {len(posts)} posts from Reddit API")
        return posts
    except Exception as e:
        logging.error(f"Error fetching Reddit data via API: {e}")
        return None

def fetch_and_process_posts_requests(notified_codes_set):
    """Fallback method: Fetches new posts from multiple subreddits using direct JSON requests."""
    import json
    
    all_posts = []
    subreddit_names = list(SUBREDDITS_CONFIG.keys())
    headers = {'User-Agent': USER_AGENT}
    params = {'limit': POST_LIMIT}
    
    logging.info(f"Fetching new posts from r/{'+'.join(subreddit_names)} using requests fallback...")
    
    # Fetch from each subreddit separately since multireddit via JSON is more complex
    for subreddit_name in subreddit_names:
        reddit_url = f"https://www.reddit.com/r/{subreddit_name}/new.json"
        
        try:
            response = requests.get(reddit_url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            
            posts_data = response.json()
            if 'data' not in posts_data or 'children' not in posts_data['data']:
                logging.warning(f"Invalid JSON data format for r/{subreddit_name}")
                continue
                
            subreddit_posts = posts_data['data']['children']
            all_posts.extend(subreddit_posts)
            logging.debug(f"Fetched {len(subreddit_posts)} posts from r/{subreddit_name}")
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching from r/{subreddit_name}: {e}")
            continue
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from r/{subreddit_name}: {e}")
            continue
    
    if all_posts:
        logging.info(f"Successfully fetched {len(all_posts)} total posts via requests fallback")
        return all_posts
    else:
        logging.error("Failed to fetch posts from any subreddit")
        return None

def fetch_and_process_posts(notified_codes_set):
    """Fetches new posts from Reddit, processes them based on flair, and notifies new codes."""
    posts = None
    using_praw = False
    
    # Try PRAW first
    praw_posts = fetch_and_process_posts_praw(notified_codes_set)
    if praw_posts is not None:
        posts = praw_posts
        using_praw = True
        logging.info("Using PRAW Reddit API")
    else:
        # Fallback to requests
        logging.warning("PRAW failed, falling back to requests method")
        requests_posts = fetch_and_process_posts_requests(notified_codes_set)
        if requests_posts is not None:
            posts = requests_posts
            using_praw = False
            logging.info("Using requests fallback method")
        else:
            logging.error("Both PRAW and requests methods failed")
            return notified_codes_set

    all_potential_codes_this_run = []
    trusted_codes_this_run = []
    processed_post_count = 0

    for post_item in posts:
        if using_praw:
            # PRAW submission object
            post_id = post_item.id
            title = post_item.title
            flair = post_item.link_flair_text  # Can be None
            selftext = post_item.selftext if post_item.selftext else ''
            author = post_item.author.name if post_item.author else '[deleted]'
            subreddit_name = post_item.subreddit.display_name
        else:
            # Requests JSON data
            if post_item.get('kind') != 't3':
                continue
            post_data = post_item.get('data', {})
            post_id = post_data.get('id', 'N/A')
            title = post_data.get('title', '')
            flair = post_data.get('link_flair_text')  # Can be None
            selftext = post_data.get('selftext', '')
            author = post_data.get('author', '[deleted]')
            subreddit_name = post_data.get('subreddit', 'unknown')

        # --- SUBREDDIT-SPECIFIC FLAIR FILTERING ---
        if subreddit_name in SUBREDDITS_CONFIG:
            allowed_flairs = SUBREDDITS_CONFIG[subreddit_name]['allowed_flairs']
            # If allowed_flairs is empty, allow all flairs for this subreddit
            if allowed_flairs and flair not in allowed_flairs:
                logging.debug(f"Skipping Post ID: {post_id} from r/{subreddit_name} due to invalid flair: '{flair}'")
                continue
        else:
            logging.debug(f"Skipping Post ID: {post_id} from unknown subreddit: '{subreddit_name}'")
            continue

        #logging.info(f"Processing Post ID: {post_id} from r/{subreddit_name} by u/{author} with flair '{flair}', Title: '{title[:50]}...'")
        processed_post_count += 1
        
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

        # Add unique codes found in this specific post to the appropriate list
        for code in set(current_post_extracted_codes):
            if author in TRUSTED_USERS:
                # Codes from trusted users are immediately trusted
                trusted_codes_this_run.append(code)
                logging.debug(f"Code {code} from trusted user u/{author} - immediate trust")
            else:
                # Regular codes need confirmation
                all_potential_codes_this_run.append(code)

    logging.info(f"Processed {processed_post_count} posts with allowed flairs.")

    # Process trusted codes first (immediate notification)
    newly_confirmed_codes = []
    if trusted_codes_this_run:
        unique_trusted_codes = set(trusted_codes_this_run)
        for code in unique_trusted_codes:
            if code not in notified_codes_set:
                logging.info(f"Trusted code from reliable user: {code}")
                newly_confirmed_codes.append(code)
            else:
                logging.debug(f"Trusted code {code} already notified.")
    
    # Process regular codes (need confirmation count >= 2)
    if all_potential_codes_this_run:
        code_counts = collections.Counter(all_potential_codes_this_run)
        logging.info(f"Regular code counts this run: {code_counts}")
        
        for code, count in code_counts.items():
            if count >= 2 and code not in notified_codes_set:
                logging.info(f"Confirmed new code: {code} (count: {count})")
                newly_confirmed_codes.append(code)
            elif code in notified_codes_set:
                logging.debug(f"Code {code} already notified.")
            elif count < 2:
                logging.debug(f"Code {code} appeared only {count} time(s), not enough for confirmation.")
    
    if not newly_confirmed_codes and not trusted_codes_this_run:
        logging.info("No new codes found in the processed posts.")
        return notified_codes_set

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
    subreddit_names = list(SUBREDDITS_CONFIG.keys())
    logging.info("Tacticus Code Scraper started (using Reddit API via PRAW).")
    logging.info(f"Monitoring subreddits: r/{', r/'.join(subreddit_names)}")
    logging.info(f"Trusted users: {', '.join(TRUSTED_USERS) if TRUSTED_USERS else 'None'}")
    for subreddit, config in SUBREDDITS_CONFIG.items():
        flairs = config['allowed_flairs']
        if flairs:
            logging.info(f"r/{subreddit} - Allowed flairs: {flairs}")
        else:
            logging.info(f"r/{subreddit} - All flairs allowed")
    
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
