#!/usr/bin/env python3
"""Production server runner using waitress WSGI."""
import signal
import sys
import os

def handler(signum, frame):
    print(f"Got signal {signum}, ignoring...", flush=True)

signal.signal(signal.SIGTERM, handler)
signal.signal(signal.SIGHUP, handler)

PORT = int(os.environ.get('PORT', 8080))

from app import app

print(f"Starting production server on port {PORT}...", flush=True)

try:
    from waitress import serve
    print(f"Using waitress (production WSGI)", flush=True)
    serve(app, host='0.0.0.0', port=PORT, threads=4, channel_timeout=120)
except ImportError:
    print("waitress not available, falling back to Flask dev server", flush=True)
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
