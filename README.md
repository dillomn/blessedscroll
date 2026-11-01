# BlessedScroll ☥

A self-hosted, pure-video video slot machine built from your personal Twitter/X Data Archive. 

Because Twitter restricts standard API scraping to your last ~3,200 likes, the only way to relive a decade of liked videos is to use your official Twitter Data Archive.

## How it Works
1. You request your Twitter Data Archive.
2. Extract the entire `twitter-xxx` folder right into the same directory as `index.html`.
3. The custom Python server intercepts requests for `like.js`, searches for your extracted folder, and serves the file dynamically.
4. The server reads `like.js` once and keeps a small queue of ready-to-play videos, looked up in the background via `api.fxtwitter.com` (falling back to `api.vxtwitter.com`). Lookups are cached in `data/cache.json`, so rolling gets faster over time.
5. The page preloads the next video while you watch, so **Next** is instant. Deleted, non-video or broken tweets are skipped automatically.
6. You get a pure, uninterrupted, full-screen video feed with zero Twitter branding.

## Features
* **Mobile-first:** full-screen player, swipe up / **Next** for a new video, tap to pause, double-tap to like.
* **Save:** over HTTPS on a phone, opens the share sheet with the video (**Save Video** → Photos). Elsewhere it downloads the mp4 from `/dl/<id>`.
* **Keyboard:** `R`/`→` next, `Space` pause, `L` like, `D` save, `M` sound.
* **Super Likes:** Found a video so good you want to save it permanently? Click **SUPER LIKE**. The python backend automatically saves the raw URL to `super_likes.txt` on the server!
* **Metadata Overlay:** Shows the original caption, date, likes, retweets, and a link back to the original post.

## Usage
1. Extract your full `twitter-xxx` archive folder into this repository.
2. Run `docker compose up -d`. This spins up the lightweight Python server.
3. Navigate to `http://localhost:9090`.

## HTTPS (homelab)
Served on the same port as http: `https://192.168.1.197:9090` (plain http redirects, except `/setup` and `/ca.crt`).
The cert comes from a local CA on ORB in `~/.blessedscroll-ca`, name-constrained to `192.168.1.197` only; the iPhone
trusts it after the one-time steps on `http://192.168.1.197:9090/setup`. HTTPS is what makes **Save** open the share
sheet (Save Video → Photos). The server cert lasts 397 days (expires 2027-12-03): re-issue it from the same CA
(see the openssl commands in git history / labdocs) and re-run `node deploy.mjs`. The phone keeps trusting the CA.

## Deploy (homelab)
Edit on ORB in `~/blessedscroll`, commit, then `node deploy.mjs` (ships `git archive HEAD` to VM02 and restarts `p90zone`).
