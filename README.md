# BlessedScroll 🏴‍☠️

A self-hosted, pure-video meme slot machine built from your personal Twitter/X Data Archive. 

Because Twitter restricts standard API scraping to your last ~3,200 likes, the only way to relive a decade of liked videos is to use your official Twitter Data Archive.

## How it Works
1. You request your Twitter Data Archive.
2. Place the `like.js` file (found inside the `data/` folder of your archive) into the same directory as `index.html`.
3. `index.html` loads the archive directly in the browser, picks a random ID, and queries the `api.vxtwitter.com` proxy to find the raw `.mp4` file.
4. If the tweet was deleted or doesn't contain a video, it instantly skips and rolls again.
5. You get a pure, uninterrupted, full-screen video feed with zero Twitter branding.

## Features
* **[R] to Reload:** Press `R` or click the header to instantly load a new video.
* **Super Likes:** Found a video so good you want to save it permanently? Click **SUPER LIKE**. The python backend automatically saves the raw URL to `super_likes.txt` on the server!
* **Metadata Overlay:** Shows the original caption, date, likes, retweets, and a link back to the original post.

## Usage
1. Place your extracted `like.js` file into the same directory as this repository.
2. Run `docker compose up -d`. This spins up a lightweight Python server.
3. Navigate to `http://localhost:9090` and hit `R`.
