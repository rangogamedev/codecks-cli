"""
Google Docs integration for codecks-cli.
OAuth2 flow, GDD fetch/parse, and sync to Codecks cards.
"""

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

import config
from config import CliError, SetupError
from cards import list_cards, list_decks, create_card, update_card


# ---------------------------------------------------------------------------
# Google OAuth2 helpers (for private Google Doc access)
# ---------------------------------------------------------------------------

def _load_gdd_tokens():
    """Load saved Google OAuth tokens from .gdd_tokens.json."""
    if not os.path.exists(config.GDD_TOKENS_PATH):
        return None
    try:
        with open(config.GDD_TOKENS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_gdd_tokens(tokens):
    """Save Google OAuth tokens to .gdd_tokens.json."""
    with open(config.GDD_TOKENS_PATH, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    # Restrict to owner-only on Unix/Mac. No-op on Windows.
    try:
        os.chmod(config.GDD_TOKENS_PATH, 0o600)
    except (OSError, NotImplementedError):
        pass


def _save_gdd_cache(content):
    """Write GDD content to cache file with restricted permissions."""
    with open(config.GDD_CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    try:
        os.chmod(config.GDD_CACHE_PATH, 0o600)
    except (OSError, NotImplementedError):
        pass


def _google_token_request(params):
    """POST to Google's token endpoint. Returns parsed JSON or None."""
    body = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(config.GOOGLE_TOKEN_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, socket.timeout, json.JSONDecodeError) as e:
        print(f"[ERROR] Google token request failed: {e}", file=sys.stderr)
        return None


def _get_google_access_token():
    """Get a valid Google access token, auto-refreshing if expired.
    Returns the access token string, or None if not configured/authorized."""
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        return None
    tokens = _load_gdd_tokens()
    if not tokens or "refresh_token" not in tokens:
        return None

    # Check if access token is still valid (60s buffer)
    expires_at = tokens.get("expires_at", 0)
    if time.time() < expires_at - 60:
        return tokens["access_token"]

    # Refresh the access token
    result = _google_token_request({
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "refresh_token": tokens["refresh_token"],
        "grant_type": "refresh_token",
    })
    if not result or "access_token" not in result:
        print("[WARN] Google token refresh failed. Run: py codecks_api.py gdd-auth",
              file=sys.stderr)
        return None

    tokens["access_token"] = result["access_token"]
    tokens["expires_at"] = time.time() + result.get("expires_in", 3600)
    # Refresh token may be rotated
    if "refresh_token" in result:
        tokens["refresh_token"] = result["refresh_token"]
    _save_gdd_tokens(tokens)
    return tokens["access_token"]


_MAX_DOC_BYTES = 10_000_000  # 10 MB safety limit for Google Doc responses


def _fetch_google_doc_content(doc_id):
    """Fetch Google Doc as markdown. Tries OAuth first, then public fallback.
    Returns content string, or None on failure."""
    export_url = (f"https://docs.google.com/document/d/{doc_id}"
                  f"/export?format=md")

    # Try 1: OAuth Bearer token
    access_token = _get_google_access_token()
    if access_token:
        req = urllib.request.Request(export_url)
        req.add_header("Authorization", f"Bearer {access_token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read(_MAX_DOC_BYTES + 1)
                if len(raw) > _MAX_DOC_BYTES:
                    raise CliError(
                        f"[ERROR] Google Doc response too large "
                        f"(>{_MAX_DOC_BYTES} bytes). Is this the right doc?")
                return raw.decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("[WARN] Google OAuth token rejected. "
                      "Run: py codecks_api.py gdd-auth", file=sys.stderr)
            else:
                print(f"[WARN] Google Doc fetch with OAuth failed (HTTP {e.code}), "
                      "trying public URL...", file=sys.stderr)
        except (urllib.error.URLError, socket.timeout) as e:
            print(f"[WARN] Google Doc OAuth fetch failed ({e}), "
                  "trying public URL...", file=sys.stderr)

    # Try 2: Public URL (no auth — works if doc is publicly shared)
    req = urllib.request.Request(export_url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(_MAX_DOC_BYTES + 1)
            if len(raw) > _MAX_DOC_BYTES:
                raise CliError(
                    f"[ERROR] Google Doc response too large "
                    f"(>{_MAX_DOC_BYTES} bytes). Is this the right doc?")
            return raw.decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("[ERROR] Google Doc not found. Check GDD_GOOGLE_DOC_URL.",
                  file=sys.stderr)
        elif e.code in (401, 403):
            if config.GOOGLE_CLIENT_ID:
                print("[ERROR] Google Doc is private. "
                      "Run: py codecks_api.py gdd-auth", file=sys.stderr)
            else:
                print("[ERROR] Google Doc is private. Set up Google OAuth to "
                      "access it. See README for setup instructions.",
                      file=sys.stderr)
        else:
            print(f"[ERROR] Google Doc fetch failed (HTTP {e.code}).",
                  file=sys.stderr)
        return None
    except (urllib.error.URLError, socket.timeout) as e:
        print(f"[ERROR] Google Doc fetch failed: {e}", file=sys.stderr)
        return None


def _run_google_auth_flow():
    """Run the OAuth2 authorization code flow with a localhost callback.
    Opens the browser for user consent, captures the code, exchanges for tokens."""
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        raise CliError("[ERROR] Google OAuth not configured. Add GOOGLE_CLIENT_ID "
                       "and GOOGLE_CLIENT_SECRET to .env\n"
                       "  See README for setup instructions.")

    # Find a free port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    redirect_uri = f"http://127.0.0.1:{port}"
    auth_code = [None]  # mutable container for closure
    server_error = [None]

    # CSRF protection (RFC 6749 §10.12)
    oauth_state = secrets.token_urlsafe(32)

    # PKCE (RFC 7636) — defense-in-depth for installed app OAuth
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")

    class _AuthHandler(http.server.BaseHTTPRequestHandler):
        """Handle the OAuth redirect callback."""
        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            if "code" in params:
                # Verify state to prevent CSRF
                returned_state = params.get("state", [None])[0]
                if returned_state != oauth_state:
                    server_error[0] = "state_mismatch"
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        b"<html><body><h2>Authorization failed "
                        b"(state mismatch).</h2>"
                        b"<p>You can close this tab.</p></body></html>"
                    )
                    return
                auth_code[0] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Authorization successful!</h2>"
                    b"<p>You can close this tab and return to the terminal.</p>"
                    b"</body></html>"
                )
            elif "error" in params:
                server_error[0] = params["error"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Authorization denied.</h2>"
                    b"<p>You can close this tab.</p></body></html>"
                )
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, format, *a):
            pass  # Suppress HTTP server logging

    # Build authorization URL
    auth_params = urllib.parse.urlencode({
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config.GOOGLE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": oauth_state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    auth_url = f"{config.GOOGLE_AUTH_URL}?{auth_params}"

    # Start local server and open browser
    server = http.server.HTTPServer(("127.0.0.1", port), _AuthHandler)
    server.timeout = 120

    print("Opening browser for Google authorization...")
    print(f"  If the browser doesn't open, visit:\n  {auth_url}")
    webbrowser.open(auth_url)

    # Wait for the callback (one request only)
    try:
        server.handle_request()
    finally:
        server.server_close()

    if server_error[0]:
        raise CliError(f"[ERROR] Authorization denied: {server_error[0]}")
    if not auth_code[0]:
        raise CliError("[ERROR] No authorization code received "
                       "(timed out after 120s).")

    # Exchange code for tokens
    result = _google_token_request({
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "code": auth_code[0],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    })
    if not result or "access_token" not in result:
        raise CliError("[ERROR] Token exchange failed.")

    tokens = {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "expires_at": time.time() + result.get("expires_in", 3600),
        "token_type": result.get("token_type", "Bearer"),
    }
    _save_gdd_tokens(tokens)
    print("Authorization successful! Google Drive access configured.")
    print(f"  Tokens saved to {config.GDD_TOKENS_PATH}")


def _revoke_google_auth():
    """Revoke Google OAuth token and delete local token file."""
    tokens = _load_gdd_tokens()
    if not tokens:
        print("No Google authorization found (nothing to revoke).")
        return

    # Revoke at Google
    token = tokens.get("refresh_token") or tokens.get("access_token")
    if token:
        body = urllib.parse.urlencode({"token": token}).encode("utf-8")
        req = urllib.request.Request(config.GOOGLE_REVOKE_URL, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    print("Token revoked at Google.")
                else:
                    print(f"[WARN] Google revoke returned status {resp.status}.",
                          file=sys.stderr)
        except (urllib.error.URLError, socket.timeout) as e:
            print(f"[WARN] Could not reach Google to revoke token: {e}",
                  file=sys.stderr)

    # Delete local file
    if os.path.exists(config.GDD_TOKENS_PATH):
        os.remove(config.GDD_TOKENS_PATH)
        print("Local tokens deleted.")


# ---------------------------------------------------------------------------
# GDD fetch, parse, and sync
# ---------------------------------------------------------------------------

def _extract_google_doc_id(url):
    """Extract document ID from a Google Docs URL or bare ID."""
    match = re.search(r'/document/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    # Maybe it's just the ID itself
    if re.match(r'^[a-zA-Z0-9_-]{20,}$', url):
        return url
    return None


def fetch_gdd(force_refresh=False, local_file=None, save_cache=False):
    """Fetch GDD content. Priority: local_file/stdin > Google Doc > cache.
    Use --file - to read from stdin (for piping from AI agent).
    Use save_cache=True to save stdin/file content to .gdd_cache.md."""
    # 1. Local file override (or stdin with "-")
    if local_file:
        if local_file == "-":
            content = sys.stdin.read()
        elif not os.path.exists(local_file):
            raise CliError(f"[ERROR] File not found: {local_file}")
        else:
            with open(local_file, "r", encoding="utf-8") as f:
                content = f.read()
        if save_cache and content.strip():
            _save_gdd_cache(content)
            print(f"[INFO] GDD cached to {config.GDD_CACHE_PATH}", file=sys.stderr)
        return content

    # 2. Google Doc fetch (OAuth -> public URL -> cache fallback)
    if config.GDD_DOC_URL:
        use_cache = (not force_refresh) and os.path.exists(config.GDD_CACHE_PATH)
        if not use_cache:
            doc_id = _extract_google_doc_id(config.GDD_DOC_URL)
            if not doc_id:
                raise CliError("[ERROR] Invalid Google Doc URL in "
                               "GDD_GOOGLE_DOC_URL.")
            content = _fetch_google_doc_content(doc_id)
            if content:
                _save_gdd_cache(content)
                return content
            # Fetch failed — try cache
            if os.path.exists(config.GDD_CACHE_PATH):
                print("[WARN] Google Doc fetch failed, using cache.",
                      file=sys.stderr)
            else:
                raise CliError("[ERROR] Google Doc fetch failed and "
                               "no cache available.")

        # Use cache
        if os.path.exists(config.GDD_CACHE_PATH):
            with open(config.GDD_CACHE_PATH, "r", encoding="utf-8") as f:
                return f.read()

    # 3. Cache-only fallback
    if os.path.exists(config.GDD_CACHE_PATH):
        with open(config.GDD_CACHE_PATH, "r", encoding="utf-8") as f:
            return f.read()

    # 4. No source configured
    raise CliError("[ERROR] No GDD source configured. Set GDD_GOOGLE_DOC_URL "
                   "in .env, use --file <path>, or pipe via --file -")


def parse_gdd(content):
    """Parse GDD markdown into structured sections with tasks.

    Returns list of sections:
    [{"section": "Core Gameplay", "tasks": [
        {"title": "...", "priority": None, "effort": None, "content": ""},
    ]}]
    """
    sections = []
    current_section = None
    current_task = None
    # Match [P:a], [E:5], or combined [P:a E:5]
    tag_re = re.compile(r'\[P:([abc])\]', re.IGNORECASE)
    effort_re = re.compile(r'\[E:(\d+)\]', re.IGNORECASE)
    combined_re = re.compile(r'\[P:([abc])\s+E:(\d+)\]', re.IGNORECASE)

    for raw_line in content.split("\n"):
        line = raw_line.rstrip()

        # ## Section heading -> new section (deck)
        if line.startswith("## "):
            section_name = line[3:].strip()
            if section_name:
                current_section = {"section": section_name, "tasks": []}
                sections.append(current_section)
                current_task = None
            continue

        # Skip # headings (document title) and blank lines
        if line.startswith("# ") or not line.strip():
            current_task = None
            continue

        # Top-level bullet: - Task title [P:a E:5]
        if re.match(r'^[-*]\s', line.lstrip()) and not re.match(r'^\s{2,}', line):
            if not current_section:
                # Tasks before any section go into "Uncategorized"
                current_section = {"section": "Uncategorized", "tasks": []}
                sections.append(current_section)

            task_text = re.sub(r'^[-*]\s+', '', line.strip())

            # Extract tags: [P:a E:5] (combined) or [P:a] [E:5] (separate)
            priority = None
            effort = None
            combined_match = combined_re.search(task_text)
            if combined_match:
                priority = combined_match.group(1).lower()
                effort = int(combined_match.group(2))
                task_text = combined_re.sub('', task_text)
            else:
                p_match = tag_re.search(task_text)
                if p_match:
                    priority = p_match.group(1).lower()
                    task_text = tag_re.sub('', task_text)
                e_match = effort_re.search(task_text)
                if e_match:
                    effort = int(e_match.group(1))
                    task_text = effort_re.sub('', task_text)

            title = task_text.strip()
            if title:
                current_task = {
                    "title": title,
                    "priority": priority,
                    "effort": effort,
                    "content": "",
                }
                current_section["tasks"].append(current_task)
            continue

        # Indented bullet: sub-item -> append to current task's content
        if re.match(r'^\s{2,}[-*]\s', line) and current_task:
            sub_text = re.sub(r'^\s+[-*]\s+', '', line)
            if current_task["content"]:
                current_task["content"] += "\n" + sub_text
            else:
                current_task["content"] = sub_text
            continue

        # Plain text after a task -> also append as content
        if current_task and line.strip() and not line.startswith("#"):
            if current_task["content"]:
                current_task["content"] += "\n" + line.strip()
            else:
                current_task["content"] = line.strip()

    return sections


def _fuzzy_match(needle, haystack_set):
    """Check if needle closely matches any title in the set.
    Returns the matching title or None. Conservative: exact or substring only."""
    needle_lower = needle.lower().strip()
    for existing in haystack_set:
        if needle_lower == existing:
            return existing
        if len(needle_lower) > 5 and len(existing) > 5:
            if needle_lower in existing or existing in needle_lower:
                return existing
    return None


def sync_gdd(sections, project_name, target_section=None, apply=False,
             quiet=False):
    """Compare GDD tasks against Codecks cards. Optionally create missing ones.

    Returns sync report dict.
    """

    # Fetch existing cards
    existing_result = list_cards(project_filter=project_name)
    existing_cards = existing_result.get("card", {})
    existing_titles = {}
    for key, card in existing_cards.items():
        title = (card.get("title") or "").lower().strip()
        if title:
            existing_titles[title] = key

    # Resolve deck names -> IDs for placement
    decks_result = list_decks()
    deck_name_to_id = {}
    for key, deck in decks_result.get("deck", {}).items():
        deck_name_to_id[deck.get("title", "").lower()] = deck.get("id")

    report = {
        "project": project_name,
        "new": [],
        "existing": [],
        "created": [],
        "errors": [],
        "total_gdd": 0,
        "applied": apply,
        "quiet": quiet,
    }

    for section in sections:
        if target_section and section["section"].lower() != target_section.lower():
            continue

        deck_id = deck_name_to_id.get(section["section"].lower())

        for task in section["tasks"]:
            report["total_gdd"] += 1
            match = _fuzzy_match(task["title"], existing_titles)

            if match:
                match_type = "exact" if match == task["title"].lower().strip() else "fuzzy"
                report["existing"].append({
                    "title": task["title"],
                    "matched_to": match,
                    "match_type": match_type,
                    "card_id": existing_titles[match],
                })
                continue

            task_entry = {
                "title": task["title"],
                "section": section["section"],
                "priority": task.get("priority"),
                "effort": task.get("effort"),
            }

            if apply:
                try:
                    result = create_card(task["title"], task.get("content"))
                    card_id = result.get("cardId", "")
                    if not card_id:
                        raise CliError(
                            "[ERROR] create_card returned no cardId "
                            f"for '{task['title']}'")
                    update_kwargs = {}
                    if deck_id:
                        update_kwargs["deckId"] = deck_id
                    if task.get("priority"):
                        update_kwargs["priority"] = task["priority"]
                    if task.get("effort"):
                        update_kwargs["effort"] = task["effort"]
                    if update_kwargs:
                        update_card(card_id, **update_kwargs)
                    task_entry["card_id"] = card_id
                    report["created"].append(task_entry)
                    # Rate limit: ~10 creates before a brief pause
                    if len(report["created"]) % 10 == 0:
                        time.sleep(1)
                except SetupError:
                    raise
                except CliError as e:
                    task_entry["error"] = str(e)
                    report["errors"].append(task_entry)
                except Exception as e:
                    task_entry["error"] = f"Unexpected: {e}"
                    report["errors"].append(task_entry)
            else:
                task_entry["deck"] = section["section"]
                if deck_id:
                    task_entry["deck_exists"] = True
                else:
                    task_entry["deck_exists"] = False
                report["new"].append(task_entry)

    return report
