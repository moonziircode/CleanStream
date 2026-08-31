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
<html lang="id" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <meta name="theme-color" content="#09090b">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="CleanStream">
  <meta name="format-detection" content="telephone=no">
  <title>CleanStream</title>
  
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Lucide Icons -->
  <script src="https://unpkg.com/lucide@latest"></script>

  <style>
    :root {
      --sat: env(safe-area-inset-top, 0px);
      --sab: env(safe-area-inset-bottom, 0px);
      --sal: env(safe-area-inset-left, 0px);
      --sar: env(safe-area-inset-right, 0px);
    }
    
    * {
      -webkit-tap-highlight-color: transparent;
      touch-action: manipulation;
    }

    body {
      background-color: #09090b;
      color: #f4f4f5;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      padding-top: max(16px, var(--sat));
      padding-bottom: max(28px, var(--sab));
      padding-left: max(16px, var(--sal));
      padding-right: max(16px, var(--sar));
      min-height: 100vh;
      min-height: -webkit-fill-available;
    }

    .ios-glass {
      background: rgba(24, 24, 27, 0.78);
      backdrop-filter: blur(24px) saturate(180%);
      -webkit-backdrop-filter: blur(24px) saturate(180%);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }

    .ios-input {
      font-size: 16px !important; /* Prevents auto-zoom on iOS Safari */
    }

    /* Springy touch feedback */
    .ios-btn:active {
      transform: scale(0.97);
      transition: transform 0.12s cubic-bezier(0.4, 0, 0.2, 1);
    }

    video {
      background: #000;
      border-radius: 18px;
      width: 100%;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.7);
    }

    /* Custom scrollbar */
    ::-webkit-scrollbar { display: none; }
  </style>
</head>
<body class="flex flex-col items-center justify-between antialiased selection:bg-rose-500 selection:text-white">

  <!-- Top Dynamic Toast / Notification -->
  <div id="toast" class="fixed top-4 z-50 transition-all duration-300 transform -translate-y-16 opacity-0 pointer-events-none">
    <div class="ios-glass px-4 py-2.5 rounded-full shadow-2xl border border-zinc-700/60 flex items-center gap-2 text-xs font-medium text-white shadow-rose-500/10">
      <span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
      <span id="toastText">Pesan</span>
    </div>
  </div>

  <!-- App Wrapper (Optimized for iPhone 13 - 390px max-width) -->
  <div class="w-full max-w-[420px] flex flex-col gap-4 mx-auto my-auto">

    <!-- Header Navigation -->
    <header class="flex items-center justify-between px-1 pt-1 pb-2">
      <div class="flex items-center gap-2.5">
        <div class="w-9 h-9 rounded-2xl bg-gradient-to-tr from-rose-500 to-rose-600 flex items-center justify-center shadow-lg shadow-rose-500/25">
          <i data-lucide="play" class="w-4 h-4 text-white fill-white ml-0.5"></i>
        </div>
        <div>
          <h1 class="text-base font-bold tracking-tight text-white flex items-center gap-1.5 leading-none">
            CleanStream
            <span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 font-semibold border border-emerald-500/20">Pro</span>
          </h1>
          <p class="text-[11px] text-zinc-400 mt-0.5">Pemutar video bebas iklan & pop-up</p>
        </div>
      </div>

      <button onclick="shareApp()" title="Bagikan Pemutar" class="ios-btn w-9 h-9 rounded-full ios-glass flex items-center justify-center text-zinc-300 hover:text-white transition">
        <i data-lucide="share" class="w-4 h-4"></i>
      </button>
    </header>

    <!-- Main Card -->
    <div class="ios-glass p-4 rounded-3xl shadow-xl flex flex-col gap-3">
      
      <!-- Input Field Container -->
      <div class="flex flex-col gap-2">
        <label class="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider px-1">
          Tautan Video
        </label>
        
        <div class="relative flex items-center">
          <div class="absolute left-3.5 text-zinc-500 pointer-events-none">
            <i data-lucide="link" class="w-4 h-4"></i>
          </div>
          
          <input 
            type="url" 
            id="urlInput" 
            placeholder="Tempel tautan video di sini..." 
            autocomplete="off" 
            autocorrect="off" 
            autocapitalize="off" 
            spellcheck="false"
            oninput="toggleClearBtn()"
            onkeydown="if(event.key==='Enter') resolveVideo()"
            class="ios-input w-full h-12 pl-10 pr-20 bg-zinc-900/90 border border-zinc-700/60 rounded-2xl text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-rose-500/80 focus:border-transparent transition"
          >
          
          <!-- Action Buttons inside Input -->
          <div class="absolute right-2 flex items-center gap-1">
            <button 
              id="btnClear" 
              onclick="clearInput()" 
              type="button" 
              class="hidden p-1.5 rounded-full text-zinc-400 hover:text-white transition"
            >
              <i data-lucide="x-circle" class="w-4 h-4 fill-zinc-700"></i>
            </button>
            <button 
              onclick="pasteFromClipboard()" 
              type="button" 
              class="ios-btn px-2.5 py-1 rounded-xl bg-zinc-800 text-[11px] font-medium text-zinc-300 hover:text-white transition active:bg-zinc-700"
            >
              Paste
            </button>
          </div>
        </div>
      </div>

      <!-- Play Button (Full Width Mobile CTA) -->
      <button 
        id="btnPlay" 
        onclick="resolveVideo()" 
        type="button" 
        class="ios-btn w-full h-12 bg-gradient-to-r from-rose-500 to-rose-600 hover:from-rose-600 hover:to-rose-700 text-white font-semibold rounded-2xl text-sm transition shadow-lg shadow-rose-500/25 flex items-center justify-center gap-2"
      >
        <i data-lucide="play-circle" class="w-5 h-5"></i>
        <span>Putar Sekarang</span>
      </button>

    </div>

    <!-- Error Alert Banner -->
    <div id="errorAlert" class="hidden ios-glass p-3.5 rounded-2xl border-rose-500/30 bg-rose-500/10 text-rose-300 text-xs flex items-start gap-2.5 animate-fade-in">
      <i data-lucide="alert-circle" class="w-4 h-4 text-rose-400 shrink-0 mt-0.5"></i>
      <div id="errorMessage" class="leading-relaxed">Terjadi kesalahan</div>
    </div>

    <!-- Video Player Section -->
    <div id="playerSection" class="hidden flex flex-col gap-3">
      <div class="relative overflow-hidden rounded-3xl ios-glass p-1.5">
        <video 
          id="videoPlayer" 
          controls 
          playsinline 
          webkit-playsinline 
          preload="metadata"
          class="w-full aspect-video"
        >
          Browser Anda tidak mendukung pemutar HTML5.
        </video>
      </div>

      <!-- Video Action Tiles (iPhone Grid) -->
      <div class="grid grid-cols-3 gap-2">
        <button 
          onclick="shareVideo()" 
          class="ios-btn ios-glass p-3 rounded-2xl flex flex-col items-center justify-center gap-1.5 hover:bg-zinc-800 transition"
        >
          <div class="w-8 h-8 rounded-full bg-rose-500/15 text-rose-400 flex items-center justify-center">
            <i data-lucide="share-2" class="w-4 h-4"></i>
          </div>
          <span class="text-[11px] font-medium text-zinc-300">Bagikan</span>
        </button>

        <a 
          id="btnDownload" 
          href="#" 
          download 
          class="ios-btn ios-glass p-3 rounded-2xl flex flex-col items-center justify-center gap-1.5 hover:bg-zinc-800 transition"
        >
          <div class="w-8 h-8 rounded-full bg-indigo-500/15 text-indigo-400 flex items-center justify-center">
            <i data-lucide="download" class="w-4 h-4"></i>
          </div>
          <span class="text-[11px] font-medium text-zinc-300">Unduh</span>
        </a>

        <button 
          onclick="copyStreamUrl()" 
          class="ios-btn ios-glass p-3 rounded-2xl flex flex-col items-center justify-center gap-1.5 hover:bg-zinc-800 transition"
        >
          <div class="w-8 h-8 rounded-full bg-emerald-500/15 text-emerald-400 flex items-center justify-center">
            <i data-lucide="link-2" class="w-4 h-4"></i>
          </div>
          <span class="text-[11px] font-medium text-zinc-300">Salin Link</span>
        </button>
      </div>
    </div>

    <!-- History Inset Group List -->
    <div id="historyCard" class="hidden ios-glass p-4 rounded-3xl flex flex-col gap-2.5">
      <div class="flex items-center justify-between px-1">
        <h2 class="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
          <i data-lucide="clock" class="w-3.5 h-3.5"></i>
          Riwayat
        </h2>
        <button onclick="clearHistory()" class="text-[11px] text-zinc-500 hover:text-zinc-300 transition">
          Bersihkan
        </button>
      </div>
      <div id="historyList" class="flex flex-col gap-1.5"></div>
    </div>

  </div>

  <!-- Footer Info -->
  <footer class="text-center text-[10px] text-zinc-600 pt-6 pb-2">
    CleanStream &bull; Safe & Private Player
  </footer>

  <script>
    let currentStreamUrl = "";
    let currentVideoTitle = "Video";

    lucide.createIcons();

    function showToast(msg) {
      const toast = document.getElementById('toast');
      const toastText = document.getElementById('toastText');
      toastText.textContent = msg;
      toast.classList.remove('-translate-y-16', 'opacity-0', 'pointer-events-none');
      toast.classList.add('translate-y-0', 'opacity-100');
      
      setTimeout(() => {
        toast.classList.add('-translate-y-16', 'opacity-0', 'pointer-events-none');
        toast.classList.remove('translate-y-0', 'opacity-100');
      }, 2400);
    }

    function toggleClearBtn() {
      const val = document.getElementById('urlInput').value;
      const btnClear = document.getElementById('btnClear');
      if (val) {
        btnClear.classList.remove('hidden');
      } else {
        btnClear.classList.add('hidden');
      }
    }

    function clearInput() {
      const input = document.getElementById('urlInput');
      input.value = "";
      toggleClearBtn();
      input.focus();
    }

    async function pasteFromClipboard() {
      try {
        const text = await navigator.clipboard.readText();
        if (text) {
          const input = document.getElementById('urlInput');
          input.value = text.trim();
          toggleClearBtn();
          showToast("Tautan ditempel");
        }
      } catch (err) {
        showToast("Klik dan tahan kolom untuk menempel");
      }
    }

    async function resolveVideo() {
      const input = document.getElementById('urlInput').value.trim();
      if (!input) {
        showToast("Masukkan tautan terlebih dahulu");
        return;
      }

      const btn = document.getElementById('btnPlay');
      const errorAlert = document.getElementById('errorAlert');
      const playerSection = document.getElementById('playerSection');
      const videoPlayer = document.getElementById('videoPlayer');

      errorAlert.classList.add('hidden');
      btn.disabled = true;
      btn.innerHTML = `<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg><span>Memuat...</span>`;

      try {
        const res = await fetch(`/api/resolve?url=${encodeURIComponent(input)}`);
        const contentType = res.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
          const text = await res.text();
          throw new Error(`Gagal memuat stream (${res.status})`);
        }

        const data = await res.json();

        if (data.status !== "ok") {
          throw new Error(data.message || "Gagal memproses tautan");
        }

        const streamUrl = `/api/stream?url=${encodeURIComponent(data.raw_mp4)}`;
        currentStreamUrl = `${window.location.origin}${streamUrl}`;
        currentVideoTitle = data.title || "Video";

        videoPlayer.poster = data.poster || "";
        videoPlayer.src = streamUrl;
        
        const btnDownload = document.getElementById('btnDownload');
        btnDownload.href = streamUrl;
        btnDownload.download = `${data.video_id}.mp4`;

        playerSection.classList.remove('hidden');
        lucide.createIcons();

        // Scroll player smoothly into view on iPhone
        playerSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        videoPlayer.play().catch(() => {
          console.log("Autoplay dihalangi oleh iOS, klik tombol play manual.");
        });

        saveToHistory({
          id: data.video_id,
          raw_mp4: data.raw_mp4,
          poster: data.poster,
          title: data.title || data.video_id,
          date: new Date().toLocaleDateString('id-ID', { month: 'short', day: 'numeric' })
        });

        showToast("Video siap diputar");

      } catch (err) {
        errorAlert.classList.remove('hidden');
        document.getElementById('errorMessage').textContent = err.message || "Terjadi kesalahan";
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="play-circle" class="w-5 h-5"></i><span>Putar Sekarang</span>`;
        lucide.createIcons();
      }
    }

    function copyStreamUrl() {
      if (!currentStreamUrl) return;
      navigator.clipboard.writeText(currentStreamUrl).then(() => {
        showToast("Tautan stream tersalin!");
      }).catch(() => {
        showToast("Gagal menyalin tautan");
      });
    }

    async function shareVideo() {
      if (!currentStreamUrl) return;
      if (navigator.share) {
        try {
          await navigator.share({
            title: currentVideoTitle,
            url: currentStreamUrl
          });
        } catch (e) {}
      } else {
        copyStreamUrl();
      }
    }

    async function shareApp() {
      if (navigator.share) {
        try {
          await navigator.share({
            title: 'CleanStream Video Player',
            url: window.location.origin
          });
        } catch (e) {}
      } else {
        navigator.clipboard.writeText(window.location.origin);
        showToast("Link aplikasi tersalin!");
      }
    }

    function replayHistory(item) {
      document.getElementById('urlInput').value = item;
      toggleClearBtn();
      resolveVideo();
    }

    function saveToHistory(item) {
      let history = JSON.parse(localStorage.getItem('clean_stream_history') || '[]');
      history = history.filter(h => h.id !== item.id);
      history.unshift(item);
      if (history.length > 5) history.pop();
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
        <div onclick="replayHistory('${h.id}')" class="ios-btn flex items-center justify-between p-2.5 rounded-2xl bg-zinc-900/70 hover:bg-zinc-800/80 cursor-pointer border border-zinc-800/70 transition">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="w-8 h-8 rounded-xl bg-zinc-800 flex items-center justify-center text-zinc-400 shrink-0">
              <i data-lucide="film" class="w-4 h-4"></i>
            </div>
            <div class="truncate">
              <div class="text-xs font-semibold text-zinc-200 truncate font-mono">${h.id}</div>
              <div class="text-[10px] text-zinc-500">${h.date}</div>
            </div>
          </div>
          <i data-lucide="chevron-right" class="w-4 h-4 text-zinc-600 shrink-0"></i>
        </div>
      `).join('');
      lucide.createIcons();
    }

    function clearHistory() {
      localStorage.removeItem('clean_stream_history');
      renderHistory();
      showToast("Riwayat dibersihkan");
    }

    // Initialize
    toggleClearBtn();
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
