import json
import re
import glob
import os

print("Extracting Twitter Archive for BlessedScroll...")

# Find the like.js file
like_files = glob.glob('twitter-*/data/like.js')
if not like_files:
    print("Error: Could not find like.js in any twitter-*/data/ directory here.")
    print("Please place your extracted Twitter archive folder here and run again.")
    exit(1)

like_file = like_files[0]
print(f"Reading {like_file}...")

with open(like_file, 'r', encoding='utf-8') as f:
    raw_data = f.read()

# Strip the variable declaration to get pure JSON
json_data = re.sub(r'^window\.YTD\.like\.part0\s*=\s*', '', raw_data)

try:
    likes = json.loads(json_data)
    tweet_ids = [item['like']['tweetId'] for item in likes]
    print(f"Successfully extracted {len(tweet_ids)} tweet IDs!")
    
    with open('tweets.json', 'w') as f:
        json.dump(tweet_ids, f)
    print("Saved to tweets.json!")
    
except Exception as e:
    print(f"Error parsing JSON: {e}")
    exit(1)
