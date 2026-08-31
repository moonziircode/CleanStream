from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import json

class handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        raw_url = query.get("url", [""])[0]

        if not raw_url:
            self.send_error(400, "Parameter url diperlukan")
            return

        req_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
            self.send_error(502, "Gagal terhubung ke remote CDN")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        raw_url = query.get("url", [""])[0]

        if not raw_url:
            self.send_error(400, "Parameter url diperlukan")
            return

        range_header = self.headers.get("Range")
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://streamrizz.com/"
        }
        if range_header:
            req_headers["Range"] = range_header

        req = urllib.request.Request(raw_url, headers=req_headers)
        
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

                # Stream buffer in 64KB chunks
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

app = handler
