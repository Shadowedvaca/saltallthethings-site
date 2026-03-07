#!/usr/bin/env python3
"""One-time script to obtain a Google OAuth2 refresh token for Drive access.

Run this locally (not on the server). It opens a browser window for you to
authorize access, then prints the three values to add to .env on the server.

Usage:
    python3 scripts/get_gdrive_token.py
"""

import http.server
import json
import threading
import urllib.parse
import urllib.request

REDIRECT_URI = "http://localhost:8080"
SCOPE = "https://www.googleapis.com/auth/drive.readonly"

print("=== Google Drive OAuth2 Token Setup ===\n")
print("You'll need the Client ID and Client Secret from your OAuth2 Desktop app.")
print("(APIs & Services → Credentials → your OAuth 2.0 Client ID)\n")

CLIENT_ID = input("Client ID: ").strip()
CLIENT_SECRET = input("Client Secret: ").strip()

if not CLIENT_ID or not CLIENT_SECRET:
    print("Client ID and Client Secret are required.")
    raise SystemExit(1)

# Build the authorization URL
auth_params = urllib.parse.urlencode({
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": SCOPE,
    "access_type": "offline",
    "prompt": "consent",
})
auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{auth_params}"

# Capture the auth code via a local HTTP server
code_holder: list[str] = []


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if "code" in qs:
            code_holder.append(qs["code"][0])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorization complete. You can close this tab.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No authorization code received.")

    def log_message(self, format, *args):
        pass  # suppress request logs


server = http.server.HTTPServer(("localhost", 8080), _Handler)
t = threading.Thread(target=server.handle_request)
t.start()

print(f"\nOpen this URL in your browser to authorize:\n\n{auth_url}\n")

try:
    import webbrowser
    webbrowser.open(auth_url)
    print("(Browser opened automatically — if not, copy the URL above.)\n")
except Exception:
    pass

print("Waiting for authorization...")
t.join()

if not code_holder:
    print("No authorization code received. Exiting.")
    raise SystemExit(1)

code = code_holder[0]

# Exchange the authorization code for tokens
token_data_encoded = urllib.parse.urlencode({
    "grant_type": "authorization_code",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT_URI,
    "code": code,
}).encode()

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=token_data_encoded,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)

try:
    with urllib.request.urlopen(req) as resp:
        token_response = json.loads(resp.read())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"Token exchange failed: {e.code} {body}")
    raise SystemExit(1)

refresh_token = token_response.get("refresh_token")
if not refresh_token:
    print("No refresh token in response. Make sure you used prompt=consent.")
    print(f"Response: {token_response}")
    raise SystemExit(1)

print("\n=== SUCCESS — add these to /opt/satt-platform/.env ===\n")
print(f"GOOGLE_OAUTH_CLIENT_ID={CLIENT_ID}")
print(f"GOOGLE_OAUTH_CLIENT_SECRET={CLIENT_SECRET}")
print(f"GOOGLE_OAUTH_REFRESH_TOKEN={refresh_token}")
print("\nThen restart the service: sudo systemctl restart satt")
