#!/usr/bin/env python3
"""
CleanStream Local Server (Python Standard Library Only)
Supports:
- Direct MP4 streaming & HTTP 206 Partial Content (Range requests)
- HLS M3U8 playlist rewriting & proxying
- Fast multi-threaded request handling
"""

import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import re
import socket
import sys
import os
import time

DEFAULT_PORT = 8888

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def fetch_with_retry(req, retries=3, delay=1.0):
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(req, timeout=12)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(delay)

def rewrite_m3u8(content, base_url, proxy_prefix="/api/stream?url="):
    lines = content.splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            new_lines.append(line)
        elif stripped.startswith("#"):
            if 'URI="' in stripped:
                def replace_uri(match):
                    uri = match.group(1)
                    abs_uri = urllib.parse.urljoin(base_url, uri)
                    encoded = urllib.parse.quote(abs_uri, safe=":/%?=&@#+~")
                    return 'URI="' + proxy_prefix + encoded + '"'
                new_tag = re.sub(r'URI="([^"]+)"', replace_uri, stripped)
                new_lines.append(new_tag)
            else:
                new_lines.append(line)
        else:
            abs_url = urllib.parse.urljoin(base_url, stripped)
            encoded = urllib.parse.quote(abs_url, safe=":/%?=&@#+~")
            new_lines.append(proxy_prefix + encoded)
    return "\n".join(new_lines)

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
        
    player_path_match = re.search(r"playerPath\s*=\s*[\\'\"]([^\'\"]+)[\'\"]", iframe_html)
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
        
    raw_source = source_match.group(1).strip()
    encoded_source = urllib.parse.quote(raw_source, safe=":/%?=&@#+~")
    poster = poster_match.group(1) if poster_match else f"https://i.streamrizz.com/image/{video_id}.jpg"
    title = title_match.group(1).strip() if title_match else video_id

    is_hls = ".m3u8" in raw_source.lower()

    return {
        "video_id": video_id,
        "title": title,
        "raw_mp4": encoded_source,
        "is_hls": is_hls,
        "original_name": raw_source.split("/")[-1],
        "poster": poster,
        "embed_url": embed_url
    }

class CleanStreamHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET(head_only=True)

    def do_GET(self, head_only=False):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Web UI
        if path == "/" or path == "/index.html":
            public_index = os.path.join(os.path.dirname(__file__), "..", "public", "index.html")
            if os.path.exists(public_index):
                with open(public_index, "rb") as f:
                    content = f.read()
            else:
                content = b"CleanStream Player"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if not head_only:
                self.wfile.write(content)
            return

        # 2. API: Resolve Video
        if path == "/api/resolve" or path == "/resolve":
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

        # 3. Stream: Reverse Proxy
        if path == "/stream" or path == "/api/stream":
            raw_url = query.get("url", [""])[0]
            video_id = query.get("id", [""])[0]

            if not raw_url and video_id:
                try:
                    info = extract_video_info(video_id)
                    raw_url = info["raw_mp4"]
                except Exception as e:
                    self.send_error(500, f"Gagal mengekstrak video: {e}")
                    return

            if not raw_url:
                self.send_error(400, "Parameter url atau id diperlukan")
                return

            self.proxy_stream(raw_url, head_only=head_only)
            return

        self.send_error(404, "Halaman tidak ditemukan")

    def proxy_stream(self, remote_url, head_only=False):
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
                content_type = remote_resp.headers.get("Content-Type", "")
                is_m3u8 = ".m3u8" in remote_url.lower() or "mpegurl" in content_type.lower()
                
                if is_m3u8 and not head_only:
                    m3u8_content = remote_resp.read().decode("utf-8", errors="ignore")
                    rewritten_m3u8 = rewrite_m3u8(m3u8_content, remote_url, proxy_prefix="/api/stream?url=")
                    m3u8_bytes = rewritten_m3u8.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                    self.send_header("Content-Length", str(len(m3u8_bytes)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(m3u8_bytes)
                    return

                self.send_response(remote_resp.status)

                for h in ["Content-Type", "Content-Range", "Content-Length", "Accept-Ranges", "Last-Modified", "ETag"]:
                    val = remote_resp.headers.get(h)
                    if val:
                        self.send_header(h, val)

                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "*")
                if not remote_resp.headers.get("Accept-Ranges"):
                    self.send_header("Accept-Ranges", "bytes")

                self.end_headers()

                if head_only:
                    return

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

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

def run_server():
    import argparse
    parser = argparse.ArgumentParser(description="CleanStream Local Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to run server on")
    args = parser.parse_args()

    port = args.port
    httpd = None
    
    for p in range(port, port + 20):
        try:
            server_address = ("0.0.0.0", p)
            httpd = ThreadedHTTPServer(server_address, CleanStreamHandler)
            port = p
            break
        except OSError as e:
            if e.errno == 48:
                continue
            raise

    if not httpd:
        print(f"Error: Tidak ada port yang tersedia di rentang {args.port}-{args.port+20}")
        sys.exit(1)

    local_ip = get_local_ip()
    
    print("=" * 65)
    print(" 🚀 CleanStream Local Server Berjalan!")
    print("=" * 65)
    print(f" ▶ Buka di Komputer (Mac):  http://localhost:{port}")
    print(f" ▶ Buka di iPhone (Wi-Fi):   http://{local_ip}:{port}")
    print("=" * 65)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nMematikan server...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
