"""
codecks-cli — CLI tool for managing Codecks.io cards, decks, and projects
Usage: py codecks_api.py <command> [args...]

Global flags:
  --format table          Output as readable text instead of JSON (default: json)

Commands:
  query <json>            - Run a raw query against the API (uses session token)
  account                 - Show account info
  cards                   - List all cards
    --deck <name>           Filter by deck
    --status <s>            Filter by status (started, not_started, done, blocked)
    --project <name>        Filter cards to a specific project
    --search <text>         Search cards by title/content
    --stats                 Show card count summary instead of card list
  card <id>               - Get details for a specific card
  decks                   - List all decks
  projects                - List all projects (derived from decks)
  milestones              - List all milestones
  create <title>          - Create a card via Report Token (stable, no expiry)
    --deck <name>           Place card in a specific deck
    --project <name>        Place card in first deck of a project
    --content <text>        Card description/content
    --severity <level>      critical, high, low, or null
  update <id>             - Update card properties (uses session token)
    --status <state>        not_started, started, done, blocked, in_review
    --priority <level>      a (high), b (medium), c (low), or null
    --effort <n>            Effort estimation (number)
    --deck <name>           Move card to a different deck
    --title <text>          Rename the card
    --content <text>        Update card description
    --milestone <name>      Assign to milestone (use "none" to clear)
    --hero <parent_id>      Make this a sub-card of a hero card (use "none" to detach)
  archive|remove <id>     - Remove a card (reversible, this is the standard way)
  unarchive <id>          - Restore an archived card
  delete <id> --confirm   - PERMANENTLY delete (requires --confirm, prefer archive)
  done <id> [id...]       - Mark one or more cards as done
  start <id> [id...]      - Mark one or more cards as started
  gdd                     - Show parsed GDD task tree from Google Doc
    --refresh               Force re-fetch from Google (ignore cache)
    --file <path>           Use a local markdown file (use "-" for stdin)
  gdd-sync                - Sync GDD tasks to Codecks cards
    --project <name>        (required) Target project for card placement
    --section <name>        Sync only one GDD section
    --apply                 Actually create cards (dry-run without this)
    --refresh               Force re-fetch GDD before syncing
    --file <path>           Use a local markdown file (use "-" for stdin)
  generate-token          - Generate a new Report Token using the Access Key
    --label <text>          Label for the token (default: claude-code)
  dispatch <path> <json>  - Raw dispatch call (uses session token)
"""

import json
import os
import re
import socket
import sys
import urllib.request
import urllib.error

# Load config from .env
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key.strip()] = val.strip()
    return env


def save_env_value(key, value):
    """Update or add a key in the .env file."""
    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            lines = f.readlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")
    with open(ENV_PATH, "w") as f:
        f.writelines(lines)


env = load_env()
SESSION_TOKEN = env.get("CODECKS_TOKEN", "")
ACCESS_KEY = env.get("CODECKS_ACCESS_KEY", "")
REPORT_TOKEN = env.get("CODECKS_REPORT_TOKEN", "")
ACCOUNT = env.get("CODECKS_ACCOUNT", "")
BASE_URL = "https://api.codecks.io"
GDD_DOC_URL = env.get("GDD_GOOGLE_DOC_URL", "")
GDD_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".gdd_cache.md")


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _mask_token(token):
    """Show only first 6 chars of a token for safe logging."""
    return token[:6] + "..." if len(token) > 6 else token


def _safe_json_parse(text, context="input"):
    """Parse JSON with friendly error message on failure."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in {context}: {e.msg} at position {e.pos}",
              file=sys.stderr)
        sys.exit(1)


def _sanitize_error(body, max_len=500):
    """Truncate and clean error body for safe display."""
    if not body:
        return ""
    cleaned = re.sub(r'<[^>]+>', '', body)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "... [truncated]"
    return cleaned


# ---------------------------------------------------------------------------
# HTTP request layer
# ---------------------------------------------------------------------------

def session_request(path="/", data=None, method="POST"):
    """Make an authenticated request using the session token (at cookie).
    Used for reading data and dispatch mutations."""
    url = BASE_URL + path
    headers = {
        "X-Auth-Token": SESSION_TOKEN,
        "X-Account": ACCOUNT,
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            try:
                return json.loads(resp.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                print("[ERROR] Unexpected response from Codecks API (not valid JSON).",
                      file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        if e.code in (401, 403):
            print("[TOKEN_EXPIRED] The Codecks session token has expired. "
                  "Please provide a fresh 'at' cookie from browser DevTools "
                  "(Brave > F12 > Network > api.codecks.io request > Cookie header > at=...).",
                  file=sys.stderr)
            sys.exit(2)
        print(f"[ERROR] HTTP {e.code}: {e.reason}", file=sys.stderr)
        print(_sanitize_error(error_body), file=sys.stderr)
        sys.exit(1)
    except socket.timeout:
        print("[ERROR] Request timed out after 30 seconds. Is Codecks API reachable?",
              file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[ERROR] Connection failed: {e.reason}", file=sys.stderr)
        sys.exit(1)


def report_request(content, severity=None, email=None):
    """Create a card via the Report Token endpoint (stable, no expiry)."""
    if not REPORT_TOKEN:
        print("[ERROR] CODECKS_REPORT_TOKEN not set in .env. Run: py codecks_api.py generate-token",
              file=sys.stderr)
        sys.exit(1)
    payload = {"content": content}
    if severity:
        payload["severity"] = severity
    if email:
        payload["userEmail"] = email
    # NOTE: Token in URL query param is required by Codecks API design.
    # Mitigate by treating report tokens as rotatable credentials.
    url = f"{BASE_URL}/user-report/v1/create-report?token={REPORT_TOKEN}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            try:
                return json.loads(resp.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                print("[ERROR] Unexpected response from Codecks API (not valid JSON).",
                      file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        if e.code == 401:
            print("[ERROR] Report token is invalid or disabled. Generate a new one: "
                  "py codecks_api.py generate-token", file=sys.stderr)
            sys.exit(1)
        print(f"[ERROR] HTTP {e.code}: {e.reason}", file=sys.stderr)
        print(_sanitize_error(error_body), file=sys.stderr)
        sys.exit(1)
    except socket.timeout:
        print("[ERROR] Request timed out after 30 seconds. Is Codecks API reachable?",
              file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[ERROR] Connection failed: {e.reason}", file=sys.stderr)
        sys.exit(1)


def generate_report_token(label="claude-code"):
    """Use the Access Key to create a new Report Token and save it to .env."""
    if not ACCESS_KEY:
        print("[ERROR] CODECKS_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)
    # NOTE: Access key in URL query param is required by Codecks API design.
    url = f"{BASE_URL}/user-report/v1/create-report-token?accessKey={ACCESS_KEY}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps({"label": label}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            try:
                result = json.loads(resp.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                print("[ERROR] Unexpected response from Codecks API (not valid JSON).",
                      file=sys.stderr)
                sys.exit(1)
            if result.get("ok") and result.get("token"):
                save_env_value("CODECKS_REPORT_TOKEN", result["token"])
                return result
            print("[ERROR] Unexpected response:", result, file=sys.stderr)
            sys.exit(1)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"[ERROR] HTTP {e.code}: {e.reason}", file=sys.stderr)
        print(_sanitize_error(error_body), file=sys.stderr)
        sys.exit(1)
    except socket.timeout:
        print("[ERROR] Request timed out after 30 seconds. Is Codecks API reachable?",
              file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[ERROR] Connection failed: {e.reason}", file=sys.stderr)
        sys.exit(1)


def query(q):
    """Run a Codecks query (uses session token)."""
    result = session_request("/", {"query": q})
    result.pop("_root", None)
    return result


def warn_if_empty(result, relation):
    """Warn if a query returned no results — likely means the token expired.
    Codecks silently returns empty data instead of 401 when unauthenticated."""
    if relation not in result or not result[relation]:
        print(f"[TOKEN_EXPIRED] The Codecks session token may have expired "
              f"(query returned 0 {relation}s). Please provide a fresh 'at' "
              "cookie from browser DevTools "
              "(Brave > F12 > Network > api.codecks.io request > Cookie header > at=...).",
              file=sys.stderr)


# ---------------------------------------------------------------------------
# Config helpers (.env name mappings)
# ---------------------------------------------------------------------------

def _load_project_names():
    """Load project name mapping from CODECKS_PROJECTS env var.
    Format: id1=Name1,id2=Name2"""
    mapping = {}
    raw = env.get("CODECKS_PROJECTS", "")
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            pid, name = pair.split("=", 1)
            mapping[pid.strip()] = name.strip()
    return mapping


def _load_milestone_names():
    """Load milestone name mapping from CODECKS_MILESTONES env var.
    Format: id1=Name1,id2=Name2"""
    mapping = {}
    raw = env.get("CODECKS_MILESTONES", "")
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            mid, name = pair.split("=", 1)
            mapping[mid.strip()] = name.strip()
    return mapping


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

_cache = {}


def get_account():
    q = {"_root": [{"account": ["name", "id"]}]}
    return query(q)


def list_decks():
    if "decks" in _cache:
        return _cache["decks"]
    q = {"_root": [{"account": [{"decks": ["title", "id", "projectId"]}]}]}
    result = query(q)
    warn_if_empty(result, "deck")
    _cache["decks"] = result
    return result


def list_cards(deck_filter=None, status_filter=None, project_filter=None,
               search_filter=None):
    card_fields = ["title", "status", "priority", "deckId", "effort",
                   "createdAt", "milestoneId"]
    if search_filter:
        card_fields.append("content")
    card_query = {"visibility": "default"}
    if status_filter:
        card_query["status"] = status_filter

    # Resolve deck filter
    if deck_filter:
        decks_result = list_decks()
        deck_id = None
        for key, deck in decks_result.get("deck", {}).items():
            if deck.get("title", "").lower() == deck_filter.lower():
                deck_id = deck.get("id")
                break
        if deck_id:
            card_query["deckId"] = deck_id
        else:
            print(f"[ERROR] Deck '{deck_filter}' not found.", file=sys.stderr)
            sys.exit(1)

    q = {"_root": [{"account": [{f"cards({json.dumps(card_query)})": card_fields}]}]}
    result = query(q)
    warn_if_empty(result, "card")

    # Client-side project filter (cards don't have projectId directly)
    if project_filter:
        decks_result = list_decks()
        project_deck_ids = _get_project_deck_ids(decks_result, project_filter)
        if project_deck_ids is None:
            print(f"[ERROR] Project '{project_filter}' not found.", file=sys.stderr)
            sys.exit(1)
        filtered_cards = {}
        for key, card in result.get("card", {}).items():
            card_deck_id = card.get("deck_id") or card.get("deckId")
            if card_deck_id in project_deck_ids:
                filtered_cards[key] = card
        result["card"] = filtered_cards

    # Client-side text search
    if search_filter:
        search_lower = search_filter.lower()
        filtered_cards = {}
        for key, card in result.get("card", {}).items():
            title = (card.get("title", "") or "").lower()
            content = (card.get("content", "") or "").lower()
            if search_lower in title or search_lower in content:
                filtered_cards[key] = card
        result["card"] = filtered_cards

    return result


def _get_project_deck_ids(decks_result, project_name):
    """Return set of deck IDs belonging to a project, matched by name."""
    projects = _build_project_map(decks_result)
    for pid, info in projects.items():
        if info["name"].lower() == project_name.lower():
            return info["deck_ids"]
    return None


def _build_project_map(decks_result):
    """Build a map of projectId -> {name, deck_ids} from deck data.
    Project names come from CODECKS_PROJECTS in .env (API can't query them)."""
    project_names = _load_project_names()
    project_decks = {}
    for key, deck in decks_result.get("deck", {}).items():
        pid = deck.get("project_id") or deck.get("projectId")
        if pid:
            if pid not in project_decks:
                project_decks[pid] = {"deck_ids": set(), "deck_titles": []}
            project_decks[pid]["deck_ids"].add(deck.get("id"))
            project_decks[pid]["deck_titles"].append(deck.get("title", ""))

    # Apply names from .env mapping, fallback to projectId
    for pid, info in project_decks.items():
        info["name"] = project_names.get(pid, pid)

    return project_decks


def get_card(card_id):
    card_filter = json.dumps({"cardId": card_id, "visibility": "default"})
    q = {"_root": [{"account": [{f"cards({card_filter})": [
        "title", "status", "priority", "content", "deckId",
        "effort", "createdAt", "milestoneId",
        {"childCards": ["title", "status"]},
    ]}]}]}
    return query(q)


def list_milestones():
    """List milestones. Scans cards for milestone IDs and uses .env names."""
    milestone_names = _load_milestone_names()
    result = list_cards()
    used_ids = {}
    for key, card in result.get("card", {}).items():
        mid = card.get("milestone_id") or card.get("milestoneId")
        if mid:
            if mid not in used_ids:
                used_ids[mid] = []
            used_ids[mid].append(card.get("title", ""))
    output = {}
    for mid, name in milestone_names.items():
        output[mid] = {"name": name, "cards": used_ids.get(mid, [])}
    for mid, cards in used_ids.items():
        if mid not in output:
            output[mid] = {"name": mid, "cards": cards}
    return output


def list_projects():
    """List projects by querying decks and grouping by projectId."""
    decks_result = list_decks()
    projects = _build_project_map(decks_result)
    output = {}
    for pid, info in projects.items():
        output[pid] = {
            "name": info.get("name", pid),
            "deck_count": len(info["deck_ids"]),
            "decks": info["deck_titles"],
        }
    return output


# ---------------------------------------------------------------------------
# Enrichment (resolve IDs to human-readable names)
# ---------------------------------------------------------------------------

def _enrich_cards(cards_dict):
    """Add deck_name and milestone_name to card dicts for readability."""
    decks_result = list_decks()
    deck_names = {}
    for key, deck in decks_result.get("deck", {}).items():
        deck_names[deck.get("id")] = deck.get("title", "")

    milestone_names = _load_milestone_names()

    for key, card in cards_dict.items():
        did = card.get("deck_id") or card.get("deckId")
        if did:
            card["deck_name"] = deck_names.get(did, did)
        mid = card.get("milestone_id") or card.get("milestoneId")
        if mid:
            card["milestone_name"] = milestone_names.get(mid, mid)

    return cards_dict


def _compute_card_stats(cards_dict):
    """Compute summary statistics from card data."""
    stats = {
        "total": len(cards_dict),
        "by_status": {},
        "by_priority": {},
        "by_deck": {},
    }
    total_effort = 0
    effort_count = 0
    for key, card in cards_dict.items():
        status = card.get("status", "unknown")
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        priority = card.get("priority") or "none"
        stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1

        deck = card.get("deck_name", card.get("deck_id", "unknown"))
        stats["by_deck"][deck] = stats["by_deck"].get(deck, 0) + 1

        effort = card.get("effort")
        if effort is not None:
            total_effort += effort
            effort_count += 1

    stats["total_effort"] = total_effort
    stats["avg_effort"] = round(total_effort / effort_count, 1) if effort_count else 0
    return stats


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------

def create_card(title, content=None, severity=None):
    """Create a card using the Report Token (stable, no expiry).
    First line of content becomes the card title."""
    if content:
        full_content = title + "\n\n" + content
    else:
        full_content = title
    return report_request(full_content, severity=severity)


def update_card(card_id, **kwargs):
    """Update card properties via dispatch (uses session token).
    Supported fields: status, priority, effort, deckId, title, content,
    milestoneId, parentCardId."""
    payload = {"id": card_id}
    for key, val in kwargs.items():
        if val is not None:
            payload[key] = val
    return session_request("/dispatch/cards/update", payload)


def archive_card(card_id):
    """Archive a card (uses session token)."""
    return session_request("/dispatch/cards/update", {
        "id": card_id,
        "isArchived": True,
    })


def unarchive_card(card_id):
    """Unarchive a card (uses session token)."""
    return session_request("/dispatch/cards/update", {
        "id": card_id,
        "isArchived": False,
    })


def delete_card(card_id):
    """Delete a card — archives first, then deletes (uses session token)."""
    archive_card(card_id)
    try:
        return session_request("/dispatch/cards/bulkUpdate", {
            "ids": [card_id],
            "visibility": "deleted",
            "deleteFiles": False,
        })
    except SystemExit:
        print(f"Warning: Card {card_id} was archived but delete failed. "
              f"Use 'unarchive' to recover.", file=sys.stderr)
        raise


def bulk_status(card_ids, status):
    """Update status for multiple cards at once."""
    return session_request("/dispatch/cards/bulkUpdate", {
        "ids": card_ids,
        "status": status,
    })


def dispatch(path, data):
    """Generic dispatch call for mutations (uses session token)."""
    return session_request(f"/dispatch/{path}", data)


# ---------------------------------------------------------------------------
# Name -> ID resolution helpers
# ---------------------------------------------------------------------------

def _resolve_deck_id(deck_name):
    """Resolve deck name to ID."""
    decks_result = list_decks()
    for key, deck in decks_result.get("deck", {}).items():
        if deck.get("title", "").lower() == deck_name.lower():
            return deck.get("id")
    print(f"[ERROR] Deck '{deck_name}' not found.", file=sys.stderr)
    sys.exit(1)


def _resolve_milestone_id(milestone_name):
    """Resolve milestone name to ID using .env mapping."""
    milestone_names = _load_milestone_names()
    for mid, name in milestone_names.items():
        if name.lower() == milestone_name.lower():
            return mid
    print(f"[ERROR] Milestone '{milestone_name}' not found in CODECKS_MILESTONES. "
          "Add it to .env: CODECKS_MILESTONES=<id>=<name>", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# GDD (Game Design Document) helpers
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


def fetch_gdd(force_refresh=False, local_file=None):
    """Fetch GDD content. Priority: local_file/stdin > Google Doc > cache.
    Use --file - to read from stdin (for piping from AI agent)."""
    # 1. Local file override (or stdin with "-")
    if local_file:
        if local_file == "-":
            return sys.stdin.read()
        if not os.path.exists(local_file):
            print(f"[ERROR] File not found: {local_file}", file=sys.stderr)
            sys.exit(1)
        with open(local_file, "r", encoding="utf-8") as f:
            return f.read()

    # 2. Google Doc fetch (with cache)
    if GDD_DOC_URL:
        use_cache = (not force_refresh) and os.path.exists(GDD_CACHE_PATH)
        if not use_cache:
            doc_id = _extract_google_doc_id(GDD_DOC_URL)
            if not doc_id:
                print("[ERROR] Invalid Google Doc URL in GDD_GOOGLE_DOC_URL.",
                      file=sys.stderr)
                sys.exit(1)
            export_url = (f"https://docs.google.com/document/d/{doc_id}"
                          f"/export?format=md")
            req = urllib.request.Request(export_url)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content = resp.read().decode("utf-8")
                # Cache locally
                with open(GDD_CACHE_PATH, "w", encoding="utf-8") as f:
                    f.write(content)
                return content
            except (urllib.error.URLError, socket.timeout) as e:
                if os.path.exists(GDD_CACHE_PATH):
                    print(f"[WARN] Google Doc fetch failed ({e}), using cache.",
                          file=sys.stderr)
                else:
                    print(f"[ERROR] Failed to fetch Google Doc: {e}",
                          file=sys.stderr)
                    sys.exit(1)

        # Use cache
        if os.path.exists(GDD_CACHE_PATH):
            with open(GDD_CACHE_PATH, "r", encoding="utf-8") as f:
                return f.read()

    # 3. No source configured
    print("[ERROR] No GDD source configured. Set GDD_GOOGLE_DOC_URL in .env "
          "or use --file <path>.", file=sys.stderr)
    sys.exit(1)


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

        # ## Section heading → new section (deck)
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

        # Indented bullet: sub-item → append to current task's content
        if re.match(r'^\s{2,}[-*]\s', line) and current_task:
            sub_text = re.sub(r'^\s+[-*]\s+', '', line)
            if current_task["content"]:
                current_task["content"] += "\n" + sub_text
            else:
                current_task["content"] = sub_text
            continue

        # Plain text after a task → also append as content
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


def sync_gdd(sections, project_name, target_section=None, apply=False):
    """Compare GDD tasks against Codecks cards. Optionally create missing ones.

    Returns sync report dict.
    """
    import time as _time

    # Fetch existing cards
    existing_result = list_cards(project_filter=project_name)
    existing_cards = existing_result.get("card", {})
    existing_titles = {}
    for key, card in existing_cards.items():
        title = (card.get("title") or "").lower().strip()
        if title:
            existing_titles[title] = key

    # Resolve deck names → IDs for placement
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
                        _time.sleep(1)
                except Exception as e:
                    task_entry["error"] = str(e)
                    report["errors"].append(task_entry)
            else:
                task_entry["deck"] = section["section"]
                if deck_id:
                    task_entry["deck_exists"] = True
                else:
                    task_entry["deck_exists"] = False
                report["new"].append(task_entry)

    return report


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def pretty_print(data):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(json.dumps(data, indent=2, ensure_ascii=False))


def output(data, formatter=None, fmt="json"):
    """Output data in requested format."""
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if fmt == "table" and formatter:
        print(formatter(data))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def _mutation_response(action, card_id=None, details=None, data=None, fmt="json"):
    """Print a mutation confirmation."""
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parts = [action]
    if card_id:
        parts.append(f"card {card_id}")
    if details:
        parts.append(details)
    summary = ": ".join(parts)
    print(f"OK: {summary}")
    if fmt == "json" and data and data != {}:
        # Suppress dispatch noise (empty payload + actionId only)
        if set(data.keys()) <= {"payload", "actionId"} and data.get("payload") in (None, {}):
            return
        print(json.dumps(data, indent=2, ensure_ascii=False))


def _trunc(s, maxlen):
    """Truncate string with ellipsis indicator."""
    if not s:
        return ""
    return s[:maxlen - 1] + "\u2026" if len(s) > maxlen else s


# --- Table formatters ---

def _format_cards_table(result):
    """Format cards as a readable table."""
    cards = result.get("card", {})
    if not cards:
        return "No cards found."
    lines = []
    lines.append(f"{'Status':<14} {'Pri':<5} {'Eff':<4} {'Deck':<20} {'Title':<40} {'ID'}")
    lines.append("-" * 120)
    for key, card in cards.items():
        cid = key[:12]
        status = card.get("status", "")
        pri = card.get("priority") or "-"
        effort = str(card.get("effort") or "-")
        deck = _trunc(card.get("deck_name") or card.get("deck_id", ""), 20)
        title = _trunc(card.get("title", ""), 40)
        lines.append(f"{status:<14} {pri:<5} {effort:<4} {deck:<20} {title:<40} {key}")
    lines.append(f"\nTotal: {len(cards)} cards")
    return "\n".join(lines)


def _format_card_detail(result):
    """Format a single card with full details."""
    cards = result.get("card", {})
    if not cards:
        return "Card not found."
    lines = []
    for key, card in cards.items():
        lines.append(f"Card:      {key}")
        lines.append(f"Title:     {card.get('title', '')}")
        lines.append(f"Status:    {card.get('status', '')}")
        lines.append(f"Priority:  {card.get('priority') or 'none'}")
        lines.append(f"Effort:    {card.get('effort') or '-'}")
        lines.append(f"Deck:      {card.get('deck_name', card.get('deck_id', ''))}")
        ms = card.get("milestone_name", card.get("milestone_id"))
        lines.append(f"Milestone: {ms or '-'}")
        lines.append(f"Created:   {card.get('createdAt', '')}")
        content = card.get("content", "")
        if content:
            body_lines = content.split("\n", 1)
            body = body_lines[1].strip() if len(body_lines) > 1 else ""
            if body:
                lines.append(f"Content:   {body[:300]}")
        child_cards = card.get("childCards")
        if child_cards:
            child_data = result.get("card", {})
            lines.append(f"Sub-cards ({len(child_cards)}):")
            for ckey in child_cards[:10]:
                child = child_data.get(ckey, {})
                lines.append(f"  - [{child.get('status', '?')}] {child.get('title', ckey)}")
            if len(child_cards) > 10:
                lines.append(f"  ... and {len(child_cards) - 10} more")
        lines.append("")
    return "\n".join(lines)


def _format_decks_table(result):
    """Format decks as a readable table."""
    decks = result.get("deck", {})
    if not decks:
        return "No decks found."
    project_names = _load_project_names()
    lines = []
    lines.append(f"{'Title':<30} {'Project':<20} {'ID'}")
    lines.append("-" * 90)
    for key, deck in decks.items():
        title = _trunc(deck.get("title", ""), 30)
        pid = deck.get("project_id") or deck.get("projectId") or ""
        proj = project_names.get(pid, pid[:12])
        lines.append(f"{title:<30} {proj:<20} {deck.get('id', key)}")
    lines.append(f"\nTotal: {len(decks)} decks")
    return "\n".join(lines)


def _format_projects_table(result):
    """Format projects as a readable table."""
    if not result:
        return "No projects found."
    lines = []
    for pid, info in result.items():
        lines.append(f"Project: {info.get('name', pid)}")
        lines.append(f"  ID:    {pid}")
        lines.append(f"  Decks ({info.get('deck_count', 0)}): {', '.join(info.get('decks', []))}")
        lines.append("")
    return "\n".join(lines)


def _format_milestones_table(result):
    """Format milestones as a readable table."""
    if not result:
        return "No milestones found."
    lines = []
    for mid, info in result.items():
        name = info.get("name", mid)
        cards = info.get("cards", [])
        lines.append(f"Milestone: {name}  (ID: {mid})")
        lines.append(f"  Cards ({len(cards)}):")
        for c in cards[:8]:
            lines.append(f"    - {c}")
        if len(cards) > 8:
            lines.append(f"    ... and {len(cards) - 8} more")
        lines.append("")
    return "\n".join(lines)


def _format_stats_table(stats):
    """Format card stats as readable text."""
    lines = [f"Total cards: {stats['total']}"]
    lines.append(f"Total effort: {stats['total_effort']}  "
                 f"Avg effort: {stats['avg_effort']}")
    lines.append("")
    lines.append("By Status:")
    for status, count in sorted(stats["by_status"].items()):
        lines.append(f"  {status:<16} {count}")
    lines.append("")
    lines.append("By Priority:")
    pri_labels = {"a": "a (high)", "b": "b (medium)", "c": "c (low)", "none": "none"}
    for pri, count in sorted(stats["by_priority"].items()):
        lines.append(f"  {pri_labels.get(pri, pri):<16} {count}")
    lines.append("")
    lines.append("By Deck:")
    for deck, count in sorted(stats["by_deck"].items()):
        lines.append(f"  {deck:<24} {count}")
    return "\n".join(lines)


def _format_gdd_table(sections):
    """Format parsed GDD sections as a readable table."""
    if not sections:
        return "No tasks found in GDD."
    lines = []
    lines.append(f"{'Section':<24} {'Pri':<5} {'Eff':<5} {'Title'}")
    lines.append("-" * 90)
    total_tasks = 0
    for section in sections:
        for task in section["tasks"]:
            total_tasks += 1
            sec = _trunc(section["section"], 24)
            pri = task.get("priority") or "-"
            eff = str(task.get("effort") or "-")
            title = _trunc(task["title"], 50)
            lines.append(f"{sec:<24} {pri:<5} {eff:<5} {title}")
    lines.append(f"\nTotal: {total_tasks} tasks across {len(sections)} sections")
    return "\n".join(lines)


def _format_sync_report(report):
    """Format GDD sync report as readable text."""
    lines = []
    project = report.get("project", "?")
    applied = report.get("applied", False)

    lines.append(f"GDD Sync Report for \"{project}\"")
    lines.append("=" * 50)

    new_items = report.get("new", [])
    created_items = report.get("created", [])
    existing_items = report.get("existing", [])
    error_items = report.get("errors", [])

    if applied and created_items:
        lines.append(f"\nCREATED ({len(created_items)}):")
        for t in created_items:
            pri = f"[{t['priority']}]" if t.get("priority") else ""
            eff = f" E:{t['effort']}" if t.get("effort") else ""
            cid = t.get("card_id", "")[:12]
            lines.append(f"  {pri}{eff} {t['title']:<40} {cid}")
    elif new_items:
        lines.append(f"\nNEW (will be created with --apply) ({len(new_items)}):")
        for t in new_items:
            pri = f"[{t['priority']}]" if t.get("priority") else ""
            eff = f" E:{t['effort']}" if t.get("effort") else ""
            deck = t.get("deck", "?")
            exists = "" if t.get("deck_exists") else " (new deck)"
            lines.append(f"  {pri}{eff} {t['title']:<40} -> {deck}{exists}")

    if existing_items:
        lines.append(f"\nALREADY TRACKED ({len(existing_items)}):")
        for t in existing_items:
            sym = "=" if t["match_type"] == "exact" else "\u2248"
            lines.append(f"  {t['title']:<40} {sym} \"{t['matched_to']}\"")

    if error_items:
        lines.append(f"\nERRORS ({len(error_items)}):")
        for t in error_items:
            lines.append(f"  {t['title']}: {t.get('error', '?')}")

    lines.append("")
    total = report.get("total_gdd", 0)
    n_new = len(created_items) if applied else len(new_items)
    n_existing = len(existing_items)
    action = "created" if applied else "to create"
    lines.append(f"Summary: {n_new} {action}, {n_existing} existing, "
                 f"{total} total in GDD")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI flag parsing
# ---------------------------------------------------------------------------

def parse_flags(args, flag_names, bool_flag_names=None):
    """Parse --flag value pairs and --boolean flags from args.
    Returns (dict_of_flags, remaining_args)."""
    bool_flag_names = bool_flag_names or []
    flags = {}
    remaining = []
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            name = args[i][2:]
            if name in bool_flag_names:
                flags[name] = True
                i += 1
            elif name in flag_names and i + 1 < len(args):
                flags[name] = args[i + 1]
                i += 2
            else:
                remaining.append(args[i])
                i += 1
        else:
            remaining.append(args[i])
            i += 1
    return flags, remaining


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    # Extract global --format flag before command dispatch
    all_args = sys.argv[1:]
    global_flags, all_args = parse_flags(all_args, ["format"])
    fmt = global_flags.get("format", "json")

    if not all_args:
        print(__doc__)
        sys.exit(0)

    cmd = all_args[0].lower()
    args = all_args[1:]

    if cmd == "query":
        if not args:
            print("Usage: py codecks_api.py query '<json>'", file=sys.stderr)
            sys.exit(1)
        q = _safe_json_parse(args[0], "query")
        output(query(q), fmt=fmt)

    elif cmd == "account":
        output(get_account(), fmt=fmt)

    elif cmd == "decks":
        output(list_decks(), _format_decks_table, fmt)

    elif cmd == "projects":
        output(list_projects(), _format_projects_table, fmt)

    elif cmd == "milestones":
        output(list_milestones(), _format_milestones_table, fmt)

    elif cmd == "cards":
        flags, _ = parse_flags(args, ["deck", "status", "project", "search"],
                               bool_flag_names=["stats"])
        result = list_cards(
            deck_filter=flags.get("deck"),
            status_filter=flags.get("status"),
            project_filter=flags.get("project"),
            search_filter=flags.get("search"),
        )
        # Enrich cards with deck/milestone names
        result["card"] = _enrich_cards(result.get("card", {}))

        if flags.get("stats"):
            stats = _compute_card_stats(result.get("card", {}))
            output(stats, _format_stats_table, fmt)
        else:
            output(result, _format_cards_table, fmt)

    elif cmd == "card":
        if not args:
            print("Usage: py codecks_api.py card <card_id>", file=sys.stderr)
            sys.exit(1)
        result = get_card(args[0])
        result["card"] = _enrich_cards(result.get("card", {}))
        output(result, _format_card_detail, fmt)

    elif cmd == "create":
        if not args:
            print("Usage: py codecks_api.py create <title> [--deck <name>] "
                  "[--project <name>] [--content <text>] [--severity critical|high|low]",
                  file=sys.stderr)
            sys.exit(1)
        title = args[0]
        flags, _ = parse_flags(args[1:], ["content", "severity", "deck", "project"])
        result = create_card(title, flags.get("content"), flags.get("severity"))
        card_id = result.get("cardId", "")
        # Optionally move to a specific deck or project's first deck
        placed_in = None
        if flags.get("deck"):
            deck_id = _resolve_deck_id(flags["deck"])
            update_card(card_id, deckId=deck_id)
            placed_in = flags["deck"]
        elif flags.get("project"):
            decks_result = list_decks()
            project_deck_ids = _get_project_deck_ids(decks_result, flags["project"])
            if project_deck_ids:
                update_card(card_id, deckId=next(iter(project_deck_ids)))
                placed_in = flags["project"]
            else:
                print(f"[ERROR] Project '{flags['project']}' not found.",
                      file=sys.stderr)
        detail = f"title='{title}'"
        if placed_in:
            detail += f", deck='{placed_in}'"
        _mutation_response("Created", card_id, detail, result, fmt)

    elif cmd == "update":
        if not args:
            print("Usage: py codecks_api.py update <id> [--status ...] [--priority ...] "
                  "[--effort ...] [--deck ...] [--title ...] [--content ...] "
                  "[--milestone ...] [--hero ...]", file=sys.stderr)
            sys.exit(1)
        card_id = args[0]
        flags, _ = parse_flags(args[1:], [
            "status", "priority", "effort", "deck", "title", "content",
            "milestone", "hero",
        ])

        update_kwargs = {}

        if "status" in flags:
            update_kwargs["status"] = flags["status"]

        if "priority" in flags:
            val = flags["priority"]
            update_kwargs["priority"] = None if val == "null" else val

        if "effort" in flags:
            val = flags["effort"]
            if val == "null":
                update_kwargs["effort"] = None
            else:
                try:
                    update_kwargs["effort"] = int(val)
                except ValueError:
                    print(f"[ERROR] Invalid effort value '{val}': must be a number or 'null'",
                          file=sys.stderr)
                    sys.exit(1)

        if "deck" in flags:
            update_kwargs["deckId"] = _resolve_deck_id(flags["deck"])

        if "title" in flags:
            # Title = first line of content. Fetch current content, replace first line.
            card_data = get_card(card_id)
            for k, c in card_data.get("card", {}).items():
                old_content = c.get("content", "")
                parts = old_content.split("\n", 1)
                new_content = flags["title"] + ("\n" + parts[1] if len(parts) > 1 else "")
                update_kwargs["content"] = new_content
                break

        if "content" in flags:
            update_kwargs["content"] = flags["content"]

        if "milestone" in flags:
            val = flags["milestone"]
            if val.lower() == "none":
                update_kwargs["milestoneId"] = None
            else:
                update_kwargs["milestoneId"] = _resolve_milestone_id(val)

        if "hero" in flags:
            val = flags["hero"]
            if val.lower() == "none":
                update_kwargs["parentCardId"] = None
            else:
                update_kwargs["parentCardId"] = val

        if not update_kwargs:
            print("[ERROR] No update flags provided. Use --status, --priority, --effort, etc.",
                  file=sys.stderr)
            sys.exit(1)

        result = update_card(card_id, **update_kwargs)
        detail_parts = [f"{k}={v}" for k, v in update_kwargs.items()]
        _mutation_response("Updated", card_id, ", ".join(detail_parts), result, fmt)

    elif cmd in ("archive", "remove"):
        if not args:
            print("Usage: py codecks_api.py archive <card_id>", file=sys.stderr)
            sys.exit(1)
        result = archive_card(args[0])
        _mutation_response("Archived", args[0], data=result, fmt=fmt)

    elif cmd == "unarchive":
        if not args:
            print("Usage: py codecks_api.py unarchive <card_id>", file=sys.stderr)
            sys.exit(1)
        result = unarchive_card(args[0])
        _mutation_response("Unarchived", args[0], data=result, fmt=fmt)

    elif cmd == "delete":
        if not args:
            print("Usage: py codecks_api.py delete <card_id> --confirm", file=sys.stderr)
            sys.exit(1)
        flags, remaining = parse_flags(args, [], bool_flag_names=["confirm"])
        card_id = remaining[0] if remaining else args[0]
        if not flags.get("confirm"):
            print("[ERROR] Permanent deletion requires --confirm flag.", file=sys.stderr)
            print(f"Did you mean: py codecks_api.py archive {card_id}",
                  file=sys.stderr)
            sys.exit(1)
        result = delete_card(card_id)
        _mutation_response("Deleted", card_id, data=result, fmt=fmt)

    elif cmd == "done":
        if not args:
            print("Usage: py codecks_api.py done <card_id> [card_id...]", file=sys.stderr)
            sys.exit(1)
        result = bulk_status(args, "done")
        _mutation_response("Marked done", details=f"{len(args)} card(s)", data=result, fmt=fmt)

    elif cmd == "start":
        if not args:
            print("Usage: py codecks_api.py start <card_id> [card_id...]", file=sys.stderr)
            sys.exit(1)
        result = bulk_status(args, "started")
        _mutation_response("Marked started", details=f"{len(args)} card(s)",
                           data=result, fmt=fmt)

    elif cmd == "generate-token":
        flags, _ = parse_flags(args, ["label"])
        label = flags.get("label", "claude-code")
        result = generate_report_token(label)
        print(f"Report Token created: {_mask_token(result['token'])}")
        print("Full token saved to .env as CODECKS_REPORT_TOKEN")

    elif cmd == "gdd":
        flags, _ = parse_flags(args, ["file"], bool_flag_names=["refresh"])
        content = fetch_gdd(
            force_refresh=flags.get("refresh", False),
            local_file=flags.get("file"),
        )
        sections = parse_gdd(content)
        output(sections, _format_gdd_table, fmt)

    elif cmd == "gdd-sync":
        flags, _ = parse_flags(args, ["project", "section", "file"],
                               bool_flag_names=["apply", "refresh"])
        if not flags.get("project"):
            print("[ERROR] --project is required for gdd-sync.", file=sys.stderr)
            sys.exit(1)
        content = fetch_gdd(
            force_refresh=flags.get("refresh", False),
            local_file=flags.get("file"),
        )
        sections = parse_gdd(content)
        report = sync_gdd(
            sections, flags["project"],
            target_section=flags.get("section"),
            apply=flags.get("apply", False),
        )
        output(report, _format_sync_report, fmt)

    elif cmd == "dispatch":
        if len(args) < 2:
            print("Usage: py codecks_api.py dispatch <path> '<json>'", file=sys.stderr)
            sys.exit(1)
        result = dispatch(args[0], _safe_json_parse(args[1], "dispatch data"))
        output(result, fmt=fmt)

    else:
        print(f"[ERROR] Unknown command: {cmd}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
