#!/bin/bash
# Cloud Run requires an HTTP port. Start a minimal health server, then Celery Beat (singleton).
cd /app

python -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
class H(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
    def log_message(self, *a): pass
HTTPServer(('0.0.0.0', ${PORT:-8000}), H).serve_forever()
" &

exec celery -A src.tasks.celery_app beat --loglevel=info
