import os
import logging
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("Render Server is Active and Running!".encode('utf-8'))

    def log_message(self, format, *args):
        # সাধারণ সার্ভার লগ হাইড করার জন্য
        return

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"Web server running on port {port}")
    server.serve_forever()

def keep_alive():
    """ব্যাকগ্রাউন্ডে ওয়েব সার্ভার চালু রাখার থ্রেড রান করে"""
    Thread(target=run_web_server, daemon=True).start()
