#!/usr/bin/env python3
"""
CleanStream Player - Local Server & Ad-Free Video Player
Extracts and streams Streamrizz / Vidoy videos cleanly without ads, popups, or trackers.
Compatible with Desktop browsers, iPhone / iPad Safari, and Android.
"""

import http.server
import socketserver
import urllib.request
import urllib.parse
import time
import json
import re
import socket
import sys
import os

DEFAULT_PORT = 8888

def get_local_ip():
    """Detect local LAN IP for iPhone / iPad access"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def fetch_with_retry(req, retries=3, delay=1.0):
    import time
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(req, timeout=12)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(delay)

def extract_video_info(input_url_or_id):
    """
    Extracts direct MP4 URL, thumbnail, and metadata from a Streamrizz or Vidoy link/ID.
    """
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

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>CleanStream Player - Bebas Iklan & Pop-Up</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
  <style>
    body {
      background-color: #09090b;
      color: #f4f4f5;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    .glass {
      background: rgba(24, 24, 27, 0.75);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    video {
      background: #000;
      border-radius: 12px;
      box-shadow: 0 20px 50px rgba(0,0,0,0.8);
      max-height: 70vh;
      width: 100%;
    }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #09090b; }
    ::-webkit-scrollbar-thumb { background: #27272a; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #3f3f46; }
  </style>
</head>
<body class="min-h-screen flex flex-col items-center p-4 sm:p-6 lg:p-8">

  <!-- Header -->
  <header class="w-full max-w-4xl flex items-center justify-between py-4 mb-6 border-b border-zinc-800/80">
    <div class="flex items-center space-x-3">
      <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-rose-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-rose-500/20">
        <i data-lucide="play" class="w-5 h-5 text-white fill-white"></i>
      </div>
      <div>
        <h1 class="text-xl font-bold tracking-tight text-white flex items-center gap-2">
          CleanStream
          <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">Anti-PopUp</span>
        </h1>
        <p class="text-xs text-zinc-400">Pemutar video Streamrizz & Vidoy bebas iklan untuk iPhone & Desktop</p>
      </div>
    </div>
    <div class="flex items-center gap-2">
      <button onclick="toggleQRModal()" class="px-3 py-1.5 rounded-lg glass text-xs font-medium text-zinc-300 hover:text-white hover:bg-zinc-800 transition flex items-center gap-1.5">
        <i data-lucide="smartphone" class="w-4 h-4 text-rose-400"></i>
        <span class="hidden sm:inline">Buka di iPhone</span>
      </button>
    </div>
  </header>

  <!-- Main Container -->
  <main class="w-full max-w-4xl flex flex-col gap-6">

    <!-- Input Form Card -->
    <div class="glass p-5 rounded-2xl shadow-xl">
      <label class="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-2">
        Masukkan Tautan Streamrizz / Vidoy
      </label>
      <div class="flex flex-col sm:flex-row gap-3">
        <div class="relative flex-1">
          <input 
            type="text" 
            id="urlInput" 
            placeholder="https://streamrizz.com/e/..." 
            value="https://streamrizz.com/e/j1jcke4eucd8"
            class="w-full bg-zinc-900/90 border border-zinc-700/70 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-transparent transition"
            onkeydown="if(event.key==='Enter') resolveVideo()"
          >
          <button 
            onclick="pasteFromClipboard()" 
            title="Paste dari Clipboard" 
            class="absolute right-2 top-1/2 -translate-y-1/2 px-2.5 py-1 rounded-lg bg-zinc-800 text-xs text-zinc-400 hover:text-zinc-200 transition"
          >
            Paste
          </button>
        </div>
        <button 
          id="btnPlay" 
          onclick="resolveVideo()" 
          class="px-6 py-3 bg-gradient-to-r from-rose-500 to-rose-600 hover:from-rose-600 hover:to-rose-700 active:scale-[0.98] text-white font-medium rounded-xl text-sm transition shadow-lg shadow-rose-500/25 flex items-center justify-center gap-2"
        >
          <i data-lucide="play-circle" class="w-4 h-4"></i>
          <span>Putar Sekarang</span>
        </button>
      </div>

      <!-- Quick sample pills -->
      <div class="mt-3 flex items-center gap-2 flex-wrap text-xs text-zinc-400">
        <span>Contoh Cepat:</span>
        <button onclick="setSample('https://streamrizz.com/e/l4mvca58up19')" class="px-2 py-0.5 rounded bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 transition">
          l4mvca58up19
        </button>
        <button onclick="setSample('https://streamrizz.com/e/j1jcke4eucd8')" class="px-2 py-0.5 rounded bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 transition">
          j1jcke4eucd8
        </button>
      </div>
    </div>

    <!-- Error Alert -->
    <div id="errorAlert" class="hidden glass p-4 rounded-xl border-rose-500/30 bg-rose-500/10 text-rose-300 text-sm flex items-start gap-3">
      <i data-lucide="alert-circle" class="w-5 h-5 text-rose-400 shrink-0 mt-0.5"></i>
      <div id="errorMessage">Terjadi kesalahan saat memproses video.</div>
    </div>

    <!-- Video Player Section -->
    <div id="playerSection" class="hidden flex flex-col gap-4">
      <div class="relative overflow-hidden rounded-2xl glass p-2">
        <video 
          id="videoPlayer" 
          controls 
          playsinline 
          webkit-playsinline 
          preload="metadata"
          class="w-full h-auto aspect-video rounded-xl"
        >
          Browser Anda tidak mendukung HTML5 video tag.
        </video>
      </div>

      <!-- Video Action Bar & Info -->
      <div class="glass p-4 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="text-xs px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 font-mono" id="lblVideoId">ID: -</span>
            <span class="text-xs text-emerald-400 flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Proxy Streaming Aktif
            </span>
          </div>
          <p class="text-xs text-zinc-400 mt-1 truncate max-w-md font-mono" id="lblRawSource">-</p>
        </div>

        <div class="flex items-center gap-2">
          <a 
            id="btnDownload" 
            href="#" 
            download 
            class="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium transition flex items-center gap-1.5"
          >
            <i data-lucide="download" class="w-4 h-4"></i>
            <span>Unduh MP4</span>
          </a>
          <button 
            onclick="copyStreamUrl()" 
            class="px-4 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 text-xs font-medium transition flex items-center gap-1.5"
          >
            <i data-lucide="copy" class="w-4 h-4"></i>
            <span id="btnCopyText">Salin Tautan Stream</span>
          </button>
        </div>
      </div>
    </div>

    <!-- History / Recent Section -->
    <div id="historyCard" class="hidden glass p-5 rounded-2xl">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-1.5">
          <i data-lucide="history" class="w-4 h-4 text-zinc-400"></i>
          Riwayat Pemutaran
        </h2>
        <button onclick="clearHistory()" class="text-xs text-zinc-500 hover:text-zinc-300 transition">Hapus</button>
      </div>
      <div id="historyList" class="flex flex-col gap-2"></div>
    </div>

  </main>

  <!-- iPhone QR Code Modal -->
  <div id="qrModal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
    <div class="glass max-w-sm w-full p-6 rounded-3xl text-center shadow-2xl border border-zinc-700 flex flex-col items-center">
      <div class="w-12 h-12 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-4">
        <i data-lucide="smartphone" class="w-6 h-6"></i>
      </div>
      <h3 class="text-lg font-bold text-white mb-1">Buka di iPhone / iPad</h3>
      <p class="text-xs text-zinc-400 mb-5 leading-relaxed">
        Pastikan iPhone terhubung ke jaringan Wi-Fi yang sama, lalu scan kode QR ini dengan kamera iPhone:
      </p>

      <div id="qrcode" class="p-3 bg-white rounded-2xl mb-4 shadow-inner flex items-center justify-center"></div>

      <div class="w-full bg-zinc-900/90 rounded-xl p-2.5 mb-5 font-mono text-xs text-zinc-300 truncate border border-zinc-800" id="lblLanUrl">
        http://...
      </div>

      <button onclick="toggleQRModal()" class="w-full py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium transition">
        Tutup
      </button>
    </div>
  </div>

  <script>
    const LOCAL_IP = "__LOCAL_IP__";
    const PORT = "__PORT__";
    const LAN_BASE = `http://${LOCAL_IP}:${PORT}`;

    let currentStreamUrl = "";

    lucide.createIcons();

    document.getElementById('lblLanUrl').textContent = LAN_BASE;
    new QRCode(document.getElementById("qrcode"), {
      text: LAN_BASE,
      width: 180,
      height: 180,
      colorDark : "#000000",
      colorLight : "#ffffff",
      correctLevel : QRCode.CorrectLevel.M
    });

    function toggleQRModal() {
      const modal = document.getElementById('qrModal');
      modal.classList.toggle('hidden');
    }

    function setSample(url) {
      document.getElementById('urlInput').value = url;
      resolveVideo();
    }

    async function pasteFromClipboard() {
      try {
        const text = await navigator.clipboard.readText();
        if (text) {
          document.getElementById('urlInput').value = text.trim();
        }
      } catch (err) {
        alert("Izinkan akses clipboard di browser Anda");
      }
    }

    async function resolveVideo() {
      const input = document.getElementById('urlInput').value.trim();
      if (!input) return;

      const btn = document.getElementById('btnPlay');
      const errorAlert = document.getElementById('errorAlert');
      const playerSection = document.getElementById('playerSection');
      const videoPlayer = document.getElementById('videoPlayer');

      errorAlert.classList.add('hidden');
      btn.disabled = true;
      btn.innerHTML = `<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> <span>Mengekstrak...</span>`;

      try {
        const res = await fetch(`/api/resolve?url=${encodeURIComponent(input)}`);
        const data = await res.json();

        if (data.status !== "ok") {
          throw new Error(data.message || "Gagal memproses URL");
        }

        const streamUrl = `/stream?url=${encodeURIComponent(data.raw_mp4)}`;
        currentStreamUrl = `${window.location.origin}${streamUrl}`;

        videoPlayer.poster = data.poster || "";
        videoPlayer.src = streamUrl;
        
        document.getElementById('lblVideoId').textContent = `ID: ${data.video_id}`;
        document.getElementById('lblRawSource').textContent = `Source: ${data.original_name || data.raw_mp4}`;
        
        const btnDownload = document.getElementById('btnDownload');
        btnDownload.href = streamUrl;
        btnDownload.download = `${data.video_id}.mp4`;

        playerSection.classList.remove('hidden');
        lucide.createIcons();

        videoPlayer.play().catch(() => {
          console.log("Autoplay dicegah oleh browser, silakan klik tombol play manual.");
        });

        saveToHistory({
          id: data.video_id,
          raw_mp4: data.raw_mp4,
          poster: data.poster,
          date: new Date().toLocaleDateString()
        });

      } catch (err) {
        errorAlert.classList.remove('hidden');
        document.getElementById('errorMessage').textContent = err.message || "Terjadi kesalahan sistem";
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="play-circle" class="w-4 h-4"></i> <span>Putar Sekarang</span>`;
        lucide.createIcons();
      }
    }

    function copyStreamUrl() {
      if (!currentStreamUrl) return;
      navigator.clipboard.writeText(currentStreamUrl).then(() => {
        const btn = document.getElementById('btnCopyText');
        btn.textContent = "Tersalin!";
        setTimeout(() => { btn.textContent = "Salin Tautan Stream"; }, 2000);
      });
    }

    function saveToHistory(item) {
      let history = JSON.parse(localStorage.getItem('clean_stream_history') || '[]');
      history = history.filter(h => h.id !== item.id);
      history.unshift(item);
      if (history.length > 8) history.pop();
      localStorage.setItem('clean_stream_history', JSON.stringify(history));
      renderHistory();
    }

    function renderHistory() {
      const history = JSON.parse(localStorage.getItem('clean_stream_history') || '[]');
      const card = document.getElementById('historyCard');
      const list = document.getElementById('historyList');

      if (!history.length) {
        card.classList.add('hidden');
        return;
      }

      card.classList.remove('hidden');
      list.innerHTML = history.map(h => `
        <div onclick="setSample('${h.id}')" class="flex items-center justify-between p-2.5 rounded-xl bg-zinc-900/60 hover:bg-zinc-800/80 cursor-pointer border border-zinc-800/60 transition group">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center text-zinc-400 group-hover:text-rose-400 transition">
              <i data-lucide="film" class="w-4 h-4"></i>
            </div>
            <div>
              <div class="text-xs font-semibold text-zinc-200 font-mono">${h.id}</div>
              <div class="text-[10px] text-zinc-500">${h.date}</div>
            </div>
          </div>
          <i data-lucide="chevron-right" class="w-4 h-4 text-zinc-600 group-hover:text-zinc-300 transition"></i>
        </div>
      `).join('');
      lucide.createIcons();
    }

    function clearHistory() {
      localStorage.removeItem('clean_stream_history');
      renderHistory();
    }

    renderHistory();
  </script>
</body>
</html>
"""

class CleanStreamHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {self.command} {self.path} {args[0]}\n")

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/stream":
            raw_url = query.get("url", [""])[0]
            video_id = query.get("id", [""])[0]

            if not raw_url and video_id:
                try:
                    info = extract_video_info(video_id)
                    raw_url = info["raw_mp4"]
                except Exception:
                    self.send_error(500)
                    return

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
                with fetch_with_retry(req) as resp:
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

        # 1. Web UI
        if path == "/" or path == "/index.html":
            local_ip = get_local_ip()
            content = HTML_TEMPLATE.replace("__LOCAL_IP__", local_ip).replace("__PORT__", str(self.server.server_address[1]))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
            return

        # 2. API: Resolve Video
        if path == "/api/resolve":
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
        if path == "/stream":
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

            self.proxy_stream(raw_url)
            return

        self.send_error(404, "Halaman tidak ditemukan")

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
    print(" Tekan Ctrl + C di terminal untuk menghentikan server.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nMematikan server...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
