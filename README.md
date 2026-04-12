# BlessedScroll 🏴‍☠️

A self-hosted, pure-video meme slot machine built from your personal Twitter/X Data Archive. 

Because Twitter restricts standard API scraping to your last ~3,200 likes, the only way to relive a decade of liked videos is to use your official Twitter Data Archive.

## How it Works
1. You request your Twitter Data Archive.
2. You run `extract_likes.py` on the `like.js` file to strip out all 30k+ Tweet IDs into a clean JSON array.
3. `index.html` loads the array, picks a random ID, and queries the `api.vxtwitter.com` proxy to find the raw `.mp4` file.
4. If the tweet was deleted or doesn't contain a video, it instantly skips and rolls again.
5. You get a pure, uninterrupted, full-screen video feed with zero Twitter branding.

## Features
* **[R] to Reload:** Press `R` or click the header to instantly load a new video.
* **Super Likes:** Found a video so good you want to save it permanently? Click **SUPER LIKE** and it saves the ID to your browser's local storage.
* **Export Likes:** Click **EXPORT LIKES** to instantly download a `.txt` file containing the direct links to all the memes you super-liked.
* **Metadata Overlay:** Shows the original caption, date, likes, retweets, and a link back to the original post.

## Usage
1. Place your extracted `twitter-*/data/like.js` file into the same directory as this repository.
2. Run `python3 extract_likes.py`. This generates `tweets.json`.
3. Start a local web server (e.g. `docker compose up -d`).
4. Navigate to `http://localhost:9090` and hit `R`.
