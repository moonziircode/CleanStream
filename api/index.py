from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import urllib.request
import urllib.parse
import json
import re
import time

app = Flask(__name__)
CORS(app)

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

def handle_resolve():
    url = request.args.get("url")
    if not url:
        return jsonify({"status": "error", "message": "Parameter url diperlukan"}), 400
    try:
        info = extract_video_info(url)
        return jsonify({"status": "ok", **info})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def handle_stream():
    raw_url = request.args.get("url")
    if not raw_url:
        return "Parameter url diperlukan", 400

    range_header = request.headers.get("Range")
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://streamrizz.com/"
    }
    if range_header:
        req_headers["Range"] = range_header

    req = urllib.request.Request(raw_url, headers=req_headers)
    try:
        remote_resp = urllib.request.urlopen(req, timeout=15)
        status_code = remote_resp.status

        if request.method == "HEAD":
            resp = Response(status=status_code)
            for h in ["Content-Type", "Content-Range", "Content-Length", "Accept-Ranges", "Last-Modified", "ETag"]:
                val = remote_resp.headers.get(h)
                if val:
                    resp.headers[h] = val
            resp.headers["Accept-Ranges"] = "bytes"
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp

        def generate():
            try:
                while True:
                    chunk = remote_resp.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                remote_resp.close()

        resp = Response(generate(), status=status_code)
        for h in ["Content-Type", "Content-Range", "Content-Length", "Accept-Ranges", "Last-Modified", "ETag"]:
            val = remote_resp.headers.get(h)
            if val:
                resp.headers[h] = val
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp
    except Exception as e:
        return f"Streaming error: {e}", 502

# Explicit Routes
@app.route("/api/resolve", methods=["GET"])
@app.route("/resolve", methods=["GET"])
def route_resolve():
    return handle_resolve()

@app.route("/api/stream", methods=["GET", "HEAD"])
@app.route("/stream", methods=["GET", "HEAD"])
def route_stream():
    return handle_stream()

# Catch-all Route Dispatcher (Handles Vercel rewrites or direct API calls)
@app.route("/", defaults={"path": ""}, methods=["GET", "HEAD"])
@app.route("/<path:path>", methods=["GET", "HEAD"])
def route_catch_all(path):
    p = (request.path or "").lower()
    if "stream" in p:
        return handle_stream()
    elif "resolve" in p or "url" in request.args:
        return handle_resolve()
    return jsonify({"status": "ok", "service": "CleanStream API", "path": request.path})

handler = app
