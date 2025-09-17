# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

The Tacticus Code Scraper is a Python application that monitors the r/Tacticus_Codes subreddit for new game codes and sends notifications via ntfy.sh and desktop notifications. The application scrapes Reddit posts, extracts potential codes using pattern matching, and confirms codes that appear multiple times across posts to reduce false positives.

## Development Commands

### Running the Application
```bash
python3 app.py
```
The application runs as a daemon, checking every 5 minutes (300 seconds) for new codes.

### Installing Dependencies
```bash
pip3 install -r requirements.txt
```
Requires the `requests` and `praw` libraries. PRAW (Python Reddit API Wrapper) is used for Reddit API access with automatic fallback to direct requests.

### Configuration Setup
Before running the application, ensure the `config.json` file exists with proper settings:
```bash
# The config.json file should contain Reddit API credentials and application settings
# See the Configuration section below for details
```

### Docker Operations
```bash
# Build the container
docker build -t tacticus-scraper .

# Run the container
docker run -d tacticus-scraper
```

### Testing Manual Runs
To test without the continuous loop, modify the `while True:` loop in `app.py` or run individual functions in the Python REPL:
```python
python3 -c "from app import *; notified_codes = load_notified_codes(); fetch_and_process_posts(notified_codes)"
```

## Architecture and Key Components

### Core Logic Flow
1. **Reddit API Integration**: Attempts to fetch posts using PRAW (Python Reddit API Wrapper) with API credentials, automatically falls back to direct JSON requests if API access fails
2. **Flair Filtering**: Only processes posts with specific flairs ("Codes + Referral ", "New Code")
3. **Code Extraction**: Uses regex patterns to find alphanumeric codes (3-25 chars) in titles and post bodies
4. **Code Validation**: Requires codes to appear in 2+ posts to be considered valid (reduces false positives)
5. **Dual Notifications**: Sends via ntfy.sh web service and desktop notify-send
6. **State Persistence**: Tracks notified codes in `notified_codes.txt` to prevent duplicates

### Pattern Matching System
- **Candidate codes**: `r'\b[A-Z0-9]{3,25}\b'` - finds potential codes
- **Referral code exclusion**: `r'^[A-Z]{3}-\d{2,3}-[A-Z]{3}$'` - filters out referral codes
- **Body hint patterns**: Complex regex patterns that detect when titles suggest codes are in post bodies
- **Ignored words**: Common terms like "NEW", "CODE", "CODES", "REFERRAL" are filtered out

### Configuration File Structure
All settings are now stored in `config.json`. The application loads this file at startup:

```json
{
    "reddit": {
        "client_id": "your_reddit_client_id",
        "client_secret": "your_reddit_client_secret",
        "subreddit": "Tacticus_Codes",
        "user_agent": "TacticusCodeBot/0.3 by RedditUserJoekki (Python Script with PRAW)"
    },
    "application": {
        "fetch_interval_seconds": 300,
        "post_limit": 40,
        "codes_file": "notified_codes.txt",
        "log_file": "code_scraper.log"
    },
    "notifications": {
        "ntfy_topic_url": "ntfy.sh/tacticus_codes"
    },
    "filtering": {
        "allowed_flairs": ["Codes + Referral ", "New Code"],
        "ignored_words": ["NEW", "CODE", "CODES", "REFERRAL"]
    },
    "patterns": {
        "candidate_code_pattern": "\\b[A-Z0-9]{3,25}\\b",
        "referral_code_pattern": "^[A-Z]{3}-\\d{2,3}-[A-Z]{3}$"
    }
}
```

### Configuration Validation
The application validates that all required configuration sections are present:
- `reddit`: API credentials and subreddit settings
- `application`: Runtime behavior settings
- `notifications`: Notification service configuration
- `filtering`: Content filtering rules
- `patterns`: Regex patterns for code detection

### State Files
- `notified_codes.txt`: Persistent storage of already-notified codes (one per line, uppercase)
- `code_scraper.log`: Application logs with timestamp and level
- `code_scraper.txt`: Alternative log file path used in some configurations

## Reddit API Integration

### API Credentials
The application uses Reddit API credentials stored in `config.json`:
- `reddit.client_id`: OAuth2 client ID for the Reddit application
- `reddit.client_secret`: OAuth2 client secret for the Reddit application
- Authentication uses read-only mode for public content access

**Security Note**: The `config.json` file contains sensitive API credentials. Keep this file secure and do not commit it to version control.

### Fallback Mechanism
The application implements a robust dual-approach system:
1. **Primary**: PRAW Reddit API with proper authentication
2. **Fallback**: Direct JSON requests to Reddit's public endpoints

If the API credentials fail or expire, the application automatically switches to the fallback method without interruption. This ensures continued operation even in VM environments where API access might be restricted.

## Code Modification Guidelines

### Adding New Code Patterns
To modify code detection, update the regex patterns in the `config.json` file under the `patterns` section. The system uses two-stage filtering:
1. Broad capture with `candidate_code_pattern`
2. Specific exclusions with `referral_code_pattern` and `ignored_words`

### Notification Channels
The `notify_ntfy()` function handles both web and desktop notifications. To add new notification methods, extend this function or create additional notification functions.

### Flair Management
Update the `filtering.allowed_flairs` array in `config.json` to change which Reddit post flairs are processed. Note the trailing space in "Codes + Referral " is intentional.

### Logging Configuration
Logging uses Python's standard logging module with both file and console handlers. The log file path is configured in `config.json` under `application.log_file`. To adjust log levels or formats, modify the `logging.basicConfig()` call in `app.py`.

## File Structure Context
- `app.py`: Main application with all core logic (single-file architecture)
- `config.json`: Configuration file with API credentials and application settings
- `requirements.txt`: Dependencies (requests and praw)
- `Dockerfile`: Simple Python 3.9 container setup with non-root user
- `README.md`: Basic project identifier
- Log and state files are created at runtime in the same directory
