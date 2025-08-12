#!/usr/bin/env python3
"""
Simple HTTP server to serve the frontend HTML file.
This is separate from the backend API server.
"""

import http.server
import socketserver
import os
import webbrowser
import threading
import time

PORT = 3100
DIRECTORY = "/home/ashok/Desktop/tts_test"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

def open_browser():
    """Open browser after a short delay"""
    time.sleep(1)
    webbrowser.open(f'http://localhost:{PORT}')

if __name__ == "__main__":
    os.chdir(DIRECTORY)
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"🌐 Frontend server starting on http://localhost:{PORT}")
        print(f"📁 Serving files from: {DIRECTORY}")
        print(f"🔗 Backend API should be running on http://localhost:8001")
        print(f"🚀 Opening browser...")
        print(f"🛑 Press Ctrl+C to stop")
        
        # Open browser in background
        threading.Thread(target=open_browser, daemon=True).start()
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 Frontend server stopped")