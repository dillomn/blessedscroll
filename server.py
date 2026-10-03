import http.server
import socketserver
import json
import os
import glob
import re
import urllib.request
import urllib.error

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # API Endpoint to fetch current likes
        if self.path == '/get_likes':
            urls = []
            if os.path.exists('super_likes.txt'):
                with open('super_likes.txt', 'r') as f:
                    urls = [line.strip() for line in f.readlines() if line.strip()]
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(urls).encode())
            return
            
        # Proxy tweet lookups: vxtwitter now serves a Cloudflare challenge to
        # browser user agents, so the browser can't call it directly.
        m = re.fullmatch(r'/tweet/(\d{1,25})', self.path)
        if m:
            req = urllib.request.Request(
                f'https://api.vxtwitter.com/Twitter/status/{m.group(1)}',
                headers={'User-Agent': 'BlessedScroll/1.0'})
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    status, body = r.status, r.read()
            except urllib.error.HTTPError as e:
                status, body = e.code, b'{}'
            except Exception as e:
                print("Error proxying tweet:", e)
                status, body = 502, b'{}'
            self.send_response(status)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
            return

        # Dynamically serve like.js from the messy Twitter archive folder!
        if self.path == '/like.js':
            like_files = glob.glob('twitter-*/data/like.js')
            if like_files:
                try:
                    with open(like_files[0], 'rb') as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header('Content-type', 'application/javascript')
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    print("Error reading like.js:", e)
            
            # Not found
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"// like.js not found in any twitter-*/data/ folder")
        else:
            # Serve index.html and other files normally
            super().do_GET()

    def do_POST(self):
        if self.path == '/superlike':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
                tweet_url = data.get('url')
                action = data.get('action', 'add')
                
                if tweet_url:
                    if action == 'add':
                        # Append to server-side file
                        with open('super_likes.txt', 'a') as f:
                            f.write(tweet_url + '\n')
                    elif action == 'remove':
                        # Remove from server-side file
                        if os.path.exists('super_likes.txt'):
                            with open('super_likes.txt', 'r') as f:
                                lines = f.readlines()
                            with open('super_likes.txt', 'w') as f:
                                for line in lines:
                                    if line.strip() != tweet_url.strip():
                                        f.write(line)

                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"status":"success"}')
                    return
            except Exception as e:
                print("Error processing like:", e)
            
            self.send_response(400)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

PORT = 80
print(f"BlessedScroll Server booting on port {PORT}...")
socketserver.ThreadingTCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer.daemon_threads = True
with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
