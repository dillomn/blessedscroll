import http.server
import socketserver
import json
import os

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/superlike':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
                tweet_url = data.get('url')
                
                if tweet_url:
                    # Append to server-side file
                    with open('super_likes.txt', 'a') as f:
                        f.write(tweet_url + '\n')
                    
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
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
