#!/bin/bash

# Tacticus Code Scraper - Cron Wrapper Script
# This script activates the virtual environment and runs the scraper

# Change to the script directory
cd /home/yourpath/tacticus

# Activate the virtual environment
source .venv/bin/activate

# Run the scraper
python3 app.py

# Exit with the same code as the Python script
exit $?
