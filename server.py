"""BlessedScroll server.

- Reads the Twitter archive's like.js once at startup (the browser no longer
  downloads the 6.6 MB file).
- A background worker pool looks tweets up via api.fxtwitter.com (falling back
  to api.vxtwitter.com, each politely paced with 429 cooldowns) and keeps a
  small queue of ready-to-play videos, so /random answers instantly.
- Lookups are cached to data/cache.json (videos and non-videos), so the archive
  gets cheaper to roll the more it's used.
- /dl/<id> streams the mp4 back with Content-Disposition: attachment, so iOS
  Safari offers a real download (cross-origin <a download> is ignored there).
- HTTPS on the same port (9090) using tls/server.{crt,key}, issued by a local
  CA that is name-constrained to this IP (see /setup). Plain-HTTP requests
  get only /ca.crt and /setup, everything else redirects to https://.
  HTTPS is what lets iOS "Share > Save Video" straight into Photos.
- Only an explicit set of static files is served; the Twitter archive folder
  (DMs etc.) is NOT reachable over HTTP.
"""
import collections
import glob
import http.server
import json
import os
import random
import re
import socket
import socketserver
import ssl
import threading
import time
import urllib.error
import urllib.request

PORT = int(os.environ.get('PORT', '80'))
DATA_DIR = 'data'
CACHE_FILE = os.path.join(DATA_DIR, 'cache.json')
LIKES_FILE = 'super_likes.txt'
UA = 'BlessedScroll/1.0'
POOL_TARGET = 10
WORKERS = 3
STATIC = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/super_likes.html': ('super_likes.html', 'text/html; charset=utf-8'),
    '/likes': ('super_likes.html', 'text/html; charset=utf-8'),
    '/setup': ('setup.html', 'text/html; charset=utf-8'),
    '/save.js': ('save.js', 'text/javascript; charset=utf-8'),
}
PLAIN_OK = {'/setup', '/ca.crt'}   # reachable over plain http when TLS is on
TLS_DIR = 'tls'


def make_tls_context():
    crt, key = os.path.join(TLS_DIR, 'server.crt'), os.path.join(TLS_DIR, 'server.key')
    if not (os.path.exists(crt) and os.path.exists(key)):
        print('TLS: no tls/server.crt + server.key, serving plain HTTP only')
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(crt, key)
    print('TLS: enabled (https and http share the port)')
    return ctx


TLS = make_tls_context()
VIDEO_HOST = re.compile(r'^https://video\.twimg\.com/[\w\-./%]+\.mp4(\?[\w=&\-.]*)?$')


# ---------------------------------------------------------------- archive ---
def load_ids():
    files = glob.glob('twitter-*/data/like.js')
    if not files:
        print('!! no twitter-*/data/like.js found')
        return []
    with open(files[0], encoding='utf-8') as f:
        raw = f.read()
    raw = raw[raw.index('['):]
    ids = [x['like']['tweetId'] for x in json.loads(raw)]
    print(f'loaded {len(ids)} liked tweet ids from {files[0]}')
    return ids


IDS = load_ids()

# ------------------------------------------------------------------ cache ---
cache_lock = threading.Lock()
cache = {}        # id -> compact record dict, or None (no playable video)
cache_dirty = 0

os.makedirs(DATA_DIR, exist_ok=True)
try:
    with open(CACHE_FILE, encoding='utf-8') as f:
        cache = json.load(f)
    print(f'cache: {len(cache)} entries, '
          f'{sum(1 for v in cache.values() if v)} videos')
except FileNotFoundError:
    pass
except Exception as e:
    print('cache load failed, starting fresh:', e)


def save_cache(force=False):
    global cache_dirty
    with cache_lock:
        if not cache_dirty or (not force and cache_dirty < 20):
            return
        snapshot = json.dumps(cache, separators=(',', ':'))
        cache_dirty = 0
    tmp = CACHE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(snapshot)
    os.replace(tmp, CACHE_FILE)


def _rec(tid, video, thumb, w, h, gif, text, user, name, date, likes, rts, replies, url):
    return {'id': tid, 'video': video, 'thumb': thumb or '', 'w': w, 'h': h, 'gif': gif,
            'text': text or '', 'user': user or '', 'name': name or '', 'date': date,
            'likes': likes or 0, 'retweets': rts or 0, 'replies': replies or 0, 'url': url or ''}


def compact_vx(tid, d):
    for m in d.get('media_extended') or []:
        url = m.get('url') or ''
        if m.get('type') in ('video', 'gif') and VIDEO_HOST.match(url):
            size = m.get('size') or {}
            return _rec(tid, url, m.get('thumbnail_url'), size.get('width'), size.get('height'),
                        m.get('type') == 'gif', d.get('text'), d.get('user_screen_name'),
                        d.get('user_name'), d.get('date_epoch'), d.get('likes'),
                        d.get('retweets'), d.get('replies'), d.get('tweetURL'))
    return None


def compact_fx(tid, d):
    t = d.get('tweet') or {}
    a = t.get('author') or {}
    for m in (t.get('media') or {}).get('videos') or []:
        url = m.get('url') or ''
        if VIDEO_HOST.match(url):
            return _rec(tid, url, m.get('thumbnail_url'), m.get('width'), m.get('height'),
                        m.get('type') == 'gif', t.get('text'), a.get('screen_name'),
                        a.get('name'), t.get('created_timestamp'), t.get('likes'),
                        t.get('retweets'), t.get('replies'), t.get('url'))
    return None


class Transient(Exception):
    """Upstream hiccup: don't cache, try again later."""


class Provider:
    """One lookup API with its own polite pacing and 429 cooldown."""
    def __init__(self, name, url, parse, gone_codes):
        self.name, self.url, self.parse, self.gone = name, url, parse, gone_codes
        self.lock = threading.Lock()
        self.next_at = 0.0
        self.cool_until = 0.0
        self.penalty = 15

    def cooling(self):
        return max(0.0, self.cool_until - time.time())

    def fetch(self, tid):
        with self.lock:                        # space requests >= 0.35s apart
            wait = self.next_at - time.time()
            if wait > 0:
                time.sleep(wait)
            self.next_at = time.time() + 0.35
        req = urllib.request.Request(self.url.format(tid), headers={'User-Agent': UA})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in self.gone:
                return None
            if e.code == 429:
                self.cool_until = time.time() + self.penalty
                print(f'{self.name}: 429, cooling {self.penalty}s')
                self.penalty = min(self.penalty * 2, 600)
            raise Transient(f'{self.name} HTTP {e.code}')
        except ValueError:
            return None
        except Exception as e:
            raise Transient(f'{self.name} {e}')
        self.penalty = 15
        return self.parse(tid, body)


PROVIDERS = [
    Provider('fxtwitter', 'https://api.fxtwitter.com/status/{}', compact_fx, (404, 401, 410)),
    Provider('vxtwitter', 'https://api.vxtwitter.com/Twitter/status/{}', compact_vx, (404, 401, 410)),
]


def cooldown_left():
    return min(p.cooling() for p in PROVIDERS)


def lookup(tid):
    """Return compact record or None (no playable video). Raises Transient."""
    global cache_dirty
    with cache_lock:
        if tid in cache:
            return cache[tid]
    last = None
    for p in sorted(PROVIDERS, key=lambda p: p.cooling()):
        if p.cooling():
            continue
        try:
            rec = p.fetch(tid)
            break
        except Transient as e:
            last = e
    else:
        raise last or Transient('all providers cooling down')
    with cache_lock:
        cache[tid] = rec
        cache_dirty += 1
    return rec


# ------------------------------------------------------------------- pool ---
pool = collections.deque()
pool_cv = threading.Condition()


def worker():
    backoff = 1
    while True:
        with pool_cv:
            while len(pool) >= POOL_TARGET:
                pool_cv.wait()
        if not IDS:
            time.sleep(60)
            continue
        tid = random.choice(IDS)
        try:
            rec = lookup(tid)
            backoff = 1
        except Transient as e:
            wait = max(backoff, cooldown_left())
            print(f'lookup {tid}: {e}; waiting {wait:.0f}s')
            time.sleep(wait)
            backoff = min(backoff * 2, 30)
            continue
        if rec:
            with pool_cv:
                if all(p['id'] != tid for p in pool):
                    pool.append(rec)
                    pool_cv.notify_all()
        save_cache()


def saver():
    while True:
        time.sleep(30)
        try:
            save_cache(force=True)
        except Exception as e:
            print('cache save failed:', e)


def take_random(timeout=25):
    deadline = time.time() + timeout
    with pool_cv:
        while not pool:
            left = deadline - time.time()
            if left <= 0:
                return None
            pool_cv.wait(left)
        rec = pool.popleft()
        pool_cv.notify_all()
        return rec


# ------------------------------------------------------------------ likes ---
likes_lock = threading.Lock()


def read_likes():
    if not os.path.exists(LIKES_FILE):
        return []
    with open(LIKES_FILE, encoding='utf-8') as f:
        return [l.strip() for l in f if l.strip()]


def tweet_id_of(url):
    m = re.search(r'/status/(\d+)', url or '')
    return m.group(1) if m else None


# ------------------------------------------------------------------- http ---
def safe_filename(rec):
    user = re.sub(r'[^A-Za-z0-9_]', '', rec.get('user') or '') or 'video'
    return f"{user}_{rec['id']}.mp4"


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'BlessedScroll'

    def log_message(self, fmt, *args):
        if not self.path.startswith('/random'):
            super().log_message(fmt, *args)

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def send_empty(self, status):
        self.send_response(status)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def is_https(self):
        return isinstance(self.connection, ssl.SSLSocket)

    def redirect_to_https(self):
        host = (self.headers.get('Host') or '').strip()
        if not re.fullmatch(r'[\w.\-]+(:\d+)?', host):
            return self.send_empty(400)
        self.send_response(308)
        self.send_header('Location', f'https://{host}{self.path}')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?', 1)[0]

        if TLS and not self.is_https() and path not in PLAIN_OK:
            return self.redirect_to_https()

        if path == '/ca.crt':
            try:
                with open(os.path.join(TLS_DIR, 'ca.crt'), 'rb') as f:
                    body = f.read()
            except FileNotFoundError:
                return self.send_empty(404)
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-x509-ca-cert')
            self.send_header('Content-Disposition', 'attachment; filename="BlessedScroll-CA.crt"')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path in STATIC:
            fname, ctype = STATIC[path]
            with open(fname, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(body)
            return

        if path == '/random':
            rec = take_random()
            if rec:
                return self.send_json(rec)
            return self.send_json({'error': 'no videos ready yet'}, 503)

        if path == '/get_likes':
            with likes_lock:
                return self.send_json(read_likes())

        if path == '/status':
            with cache_lock:
                n = len(cache)
                v = sum(1 for x in cache.values() if x)
            return self.send_json({'ids': len(IDS), 'cached': n, 'videos': v,
                                   'pool': len(pool)})

        m = re.fullmatch(r'/tweet/(\d{1,25})', path)
        if m:
            try:
                rec = lookup(m.group(1))
            except Transient:
                return self.send_json({'error': 'upstream unavailable'}, 502)
            if not rec:
                return self.send_json({'error': 'no video'}, 404)
            return self.send_json(rec)

        m = re.fullmatch(r'/dl/(\d{1,25})', path)
        if m:
            return self.download(m.group(1))

        self.send_empty(404)

    def download(self, tid):
        try:
            rec = lookup(tid)
        except Transient:
            return self.send_empty(502)
        if not rec or not VIDEO_HOST.match(rec['video']):
            return self.send_empty(404)
        req = urllib.request.Request(rec['video'], headers={'User-Agent': UA})
        try:
            up = urllib.request.urlopen(req, timeout=20)
        except Exception as e:
            print('download upstream failed:', e)
            return self.send_empty(502)
        with up:
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp4')
            length = up.headers.get('Content-Length')
            if length:
                self.send_header('Content-Length', length)
            else:
                self.close_connection = True
            self.send_header('Content-Disposition',
                             f'attachment; filename="{safe_filename(rec)}"')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                while True:
                    chunk = up.read(256 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_POST(self):
        if TLS and not self.is_https():
            return self.redirect_to_https()
        if self.path != '/superlike':
            return self.send_empty(404)
        try:
            n = int(self.headers.get('Content-Length', 0))
            if n > 4096:
                return self.send_empty(413)
            data = json.loads(self.rfile.read(n))
            url = str(data.get('url') or '').strip()
            action = data.get('action', 'add')
            if not tweet_id_of(url) or not url.startswith('https://') or '\n' in url:
                return self.send_empty(400)
        except Exception:
            return self.send_empty(400)
        with likes_lock:
            likes = read_likes()
            if action == 'add' and url not in likes:
                likes.append(url)
            elif action == 'remove':
                likes = [l for l in likes if l != url]
            tmp = LIKES_FILE + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(''.join(l + '\n' for l in likes))
            os.replace(tmp, LIKES_FILE)
        self.send_json({'status': 'success'})


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def finish_request(self, request, client_address):
        # Runs in the per-connection thread: sniff the first byte, and if it's a
        # TLS handshake (0x16) wrap the socket, so http and https share one port.
        if TLS:
            try:
                request.settimeout(10)
                first = request.recv(1, socket.MSG_PEEK)
                request.settimeout(None)
                if first == b'\x16':
                    request = TLS.wrap_socket(request, server_side=True)
            except (ssl.SSLError, OSError):
                return   # handshake refused (e.g. cert not trusted yet) / client gone
        try:
            self.RequestHandlerClass(request, client_address, self)
        finally:
            if isinstance(request, ssl.SSLSocket):
                try:
                    request.close()
                except OSError:
                    pass


if __name__ == '__main__':
    for _ in range(WORKERS):
        threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=saver, daemon=True).start()
    print(f'BlessedScroll on :{PORT}')
    Server(('', PORT), Handler).serve_forever()
