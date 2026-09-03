#!/usr/bin/env python3
"""
CleanStream Unified High-Performance Local Server
Runs the exact same pure-WSGI backend (api.index.app) with multi-threading
and static file serving from public/.
"""

import os
import sys
import mimetypes
import socketserver
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler

# Ensure root is on python path to import api.index
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from api.index import app as api_app

PUBLIC_DIR = os.path.join(ROOT_DIR, "public")

class ThreadingWSGIServer(socketserver.ThreadingMixIn, WSGIServer):
    daemon_threads = True

class QuietWSGIRequestHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        # Concise single-line log for errors only
        if args and str(args[1]) not in ("200", "204", "206"):
            sys.stdout.write(f"[{self.log_date_time_string()}] {args[0]} -> {args[1]}\n")
            sys.stdout.flush()

def local_app(environ, start_response):
    path = environ.get("PATH_INFO", "")
    
    # Static frontend routing
    if not path.startswith("/api/"):
        target_path = "index.html" if path in ("", "/") else path.lstrip("/")
        file_path = os.path.join(PUBLIC_DIR, target_path)
        
        if os.path.isfile(file_path):
            mime, _ = mimetypes.guess_type(file_path)
            content_type = mime or "text/html"
            with open(file_path, "rb") as f:
                content = f.read()
            start_response("200 OK", [
                ("Content-Type", content_type),
                ("Content-Length", str(len(content))),
                ("Cache-Control", "no-cache")
            ])
            return [content]
            
    # Forward all API / streaming requests to production WSGI app
    return api_app(environ, start_response)

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    server = make_server("0.0.0.0", port, local_app, server_class=ThreadingWSGIServer, handler_class=QuietWSGIRequestHandler)
    print(f"🚀 CleanStream Local Server running on http://localhost:{port}")
    print(f"⚡ Loaded unified pure-WSGI backend (0 external dependencies)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    main()
