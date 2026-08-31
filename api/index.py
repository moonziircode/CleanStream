from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import json
import re
import time

def fetch_with_retry(req, retries=3, delay=1.0):
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(req, timeout=12)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(delay)

def extract_video_info(input_url_or_id):
    input_str = input_url_or_id.strip()
    if "http" in input_str:
        m = re.search(r"(?:/e/|/v/|/embed/|/d/|/)([a-zA-Z0-9_-]{6,32})(?:[/?#]|$)", input_str)
        if m:
            video_id = m.group(1)
        else:
            video_id = input_str.rstrip("/").split("/")[-1].split("?")[0]
    else:
        video_id = input_str.strip()

    embed_url = f"https://streamrizz.com/e/{video_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://streamrizz.com/"
    }
    
    # 1. Fetch embed page
    req = urllib.request.Request(embed_url, headers=headers)
    with fetch_with_retry(req) as resp:
        embed_html = resp.read().decode("utf-8")
        
    iframe_id_match = re.search(r"var iframeId = [\'\"]([a-f0-9]+)[\'\"]", embed_html)
    embed_token_match = re.search(r"var embedToken = [\'\"]([^\'\"]+)[\'\"]", embed_html)
    
    if not iframe_id_match or not embed_token_match:
        raise ValueError(f"Gagal mengekstrak token dari embed page (Video ID: {video_id})")
        
    iframe_id = iframe_id_match.group(1)
    embed_token = embed_token_match.group(1)
    
    # 2. Fetch iframe /ip129jk
    iframe_url = f"https://streamrizz.com/ip129jk?id={iframe_id}&t={embed_token}"
    headers["Referer"] = embed_url
    req2 = urllib.request.Request(iframe_url, headers=headers)
    with fetch_with_retry(req2) as resp2:
        iframe_html = resp2.read().decode("utf-8")
        
    player_path_match = re.search(r"playerPath\s*=\s*[\'\"]([^\'\"]+)[\'\"]", iframe_html)
    if not player_path_match:
        raise ValueError("Gagal menemukan playerPath di halaman iframe")
        
    player_path = player_path_match.group(1).replace(r"\u0026", "&")
    
    # 3. Fetch stream player page
    headers["Referer"] = iframe_url
    req3 = urllib.request.Request(player_path, headers=headers)
    with fetch_with_retry(req3) as resp3:
        stream_html = resp3.read().decode("utf-8")
        
    source_match = re.search(r"<source\s+[^>]*src=[\'\"]([^\'\"]+)[\'\"]", stream_html)
    if not source_match:
        source_match = re.search(r"<video\s+[^>]*src=[\'\"]([^\'\"]+)[\'\"]", stream_html)

    poster_match = re.search(r"poster=[\'\"]([^\'\"]+)[\'\"]", stream_html)
    title_match = re.search(r"<title>(.*?)</title>", stream_html)
    
    if not source_match:
        raise ValueError("Gagal menemukan sumber video langsung pada halaman player")
        
    raw_mp4 = source_match.group(1).strip()
    encoded_mp4 = urllib.parse.quote(raw_mp4, safe=":/%?=&@#+~")
    poster = poster_match.group(1) if poster_match else f"https://i.streamrizz.com/image/{video_id}.jpg"
    title = title_match.group(1).strip() if title_match else video_id

    return {
        "video_id": video_id,
        "title": title,
        "raw_mp4": encoded_mp4,
        "original_name": raw_mp4.split("/")[-1],
        "poster": poster,
        "embed_url": embed_url
    }

class handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if "stream" in path:
            raw_url = query.get("url", [""])[0]
            if not raw_url:
                self.send_error(400)
                return

            req_headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://streamrizz.com/"
            }
            range_header = self.headers.get("Range")
            if range_header:
                req_headers["Range"] = range_header

            try:
                req = urllib.request.Request(raw_url, headers=req_headers, method="HEAD")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    self.send_response(resp.status)
                    for h in ["Content-Type", "Content-Range", "Content-Length", "Accept-Ranges", "Last-Modified", "ETag"]:
                        val = resp.headers.get(h)
                        if val:
                            self.send_header(h, val)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
            except Exception:
                self.send_error(502)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Route 1: Resolve Video
        if "resolve" in path:
            url_param = query.get("url", [""])[0]
            if not url_param:
                self.send_json({"status": "error", "message": "Parameter url diperlukan"}, status=400)
                return

            try:
                info = extract_video_info(url_param)
                self.send_json({"status": "ok", **info})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, status=500)
            return

        # Route 2: Stream Video with Proxy
        if "stream" in path:
            raw_url = query.get("url", [""])[0]
            if not raw_url:
                self.send_error(400, "Parameter url diperlukan")
                return

            self.proxy_stream(raw_url)
            return

        # Fallback
        self.send_json({"status": "ok", "message": "CleanStream API is running"})

    def proxy_stream(self, remote_url):
        range_header = self.headers.get("Range")
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://streamrizz.com/"
        }
        if range_header:
            req_headers["Range"] = range_header

        req = urllib.request.Request(remote_url, headers=req_headers)
        
        try:
            with urllib.request.urlopen(req, timeout=15) as remote_resp:
                self.send_response(remote_resp.status)

                for h in ["Content-Type", "Content-Range", "Content-Length", "Accept-Ranges", "Last-Modified", "ETag"]:
                    val = remote_resp.headers.get(h)
                    if val:
                        self.send_header(h, val)

                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "*")
                if not remote_resp.headers.get("Accept-Ranges"):
                    self.send_header("Accept-Ranges", "bytes")
                if not remote_resp.headers.get("Content-Type"):
                    self.send_header("Content-Type", "video/mp4")

                self.end_headers()

                chunk_size = 64 * 1024
                while True:
                    chunk = remote_resp.read(chunk_size)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            if not self.wfile.closed:
                try:
                    self.send_error(502, f"Streaming error: {e}")
                except Exception:
                    pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

# Vercel entrypoint aliases
app = handler
