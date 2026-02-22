"""
Interactive setup wizard for codecks-cli.
Guides users through configuration of tokens, projects, and milestones.
"""

from codecks_cli import config
from codecks_cli._utils import _get_field
from codecks_cli.api import _mask_token, _try_call, generate_report_token, query
from codecks_cli.cards import (
    get_account,
    list_cards,
    list_decks,
    load_milestone_names,
    load_project_names,
)

# ---------------------------------------------------------------------------
# Setup discovery helpers
# ---------------------------------------------------------------------------


def _setup_discover_projects():
    """Discover projects from decks and save to .env."""
    print("Discovering projects...")
    decks_result = _try_call(list_decks)
    if not decks_result or not decks_result.get("deck"):
        print("  Could not fetch decks. Skipping project discovery.")
        return

    project_decks: dict[str, list[str]] = {}
    for _key, deck in decks_result.get("deck", {}).items():
        pid = _get_field(deck, "project_id", "projectId")
        if pid:
            if pid not in project_decks:
                project_decks[pid] = []
            project_decks[pid].append(deck.get("title", ""))

    if not project_decks:
        print("  No projects found.")
        config.save_env_value("CODECKS_PROJECTS", "")
        return

    existing_names = load_project_names()

    print(f"  Found {len(project_decks)} project(s):\n")
    project_pairs = []
    for pid, deck_titles in project_decks.items():
        existing_name = existing_names.get(pid)
        decks_preview = ", ".join(deck_titles[:5])
        if len(deck_titles) > 5:
            decks_preview += f" (+{len(deck_titles) - 5} more)"
        print(f"    Decks: {decks_preview}")

        if existing_name:
            name_input = input(f"    Project name [{existing_name}]: ").strip()
            name = name_input if name_input else existing_name
        else:
            name = input("    Give this project a name: ").strip()
            if not name:
                name = deck_titles[0] if deck_titles else pid[:8]
                print(f"      Using: {name}")
        project_pairs.append(f"{pid}={name}")
        print()

    config.save_env_value("CODECKS_PROJECTS", ",".join(project_pairs))
    print(f"  Saved {len(project_pairs)} project(s) to .env\n")


def _setup_discover_milestones():
    """Discover milestones from cards and save to .env."""
    print("Discovering milestones...")
    cards_result = _try_call(list_cards)
    if not cards_result or not cards_result.get("card"):
        print("  Could not fetch cards. Skipping milestone discovery.")
        return

    # Group cards by milestone
    milestone_cards: dict[str, list[str]] = {}
    for _key, card in cards_result.get("card", {}).items():
        mid = _get_field(card, "milestone_id", "milestoneId")
        if mid:
            if mid not in milestone_cards:
                milestone_cards[mid] = []
            title = card.get("title", "")
            if title:
                milestone_cards[mid].append(title)

    if not milestone_cards:
        print("  No milestones found in your cards.")
        config.save_env_value("CODECKS_MILESTONES", "")
        return

    existing_names = load_milestone_names()

    print(f"  Found {len(milestone_cards)} milestone(s):\n")
    milestone_pairs = []
    for mid, card_titles in milestone_cards.items():
        existing_name = existing_names.get(mid)
        # Show sample cards to help user identify the milestone
        sample = ", ".join(card_titles[:3])
        if len(card_titles) > 3:
            sample += f" (+{len(card_titles) - 3} more)"
        print(f"    Cards in this milestone: {sample}")

        if existing_name:
            name_input = input(f"    Milestone name [{existing_name}]: ").strip()
            name = name_input if name_input else existing_name
        else:
            name = input("    Give this milestone a name: ").strip()
            if not name:
                name = mid[:8]
                print(f"      Using: {name}")
        milestone_pairs.append(f"{mid}={name}")
        print()

    config.save_env_value("CODECKS_MILESTONES", ",".join(milestone_pairs))
    print(f"  Saved {len(milestone_pairs)} milestone(s) to .env\n")


def _setup_discover_user():
    """Discover current user ID from account roles and save to .env."""
    print("Discovering your user ID...")
    result = _try_call(
        query, {"_root": [{"account": [{"roles": ["userId", "role", {"user": ["id", "name"]}]}]}]}
    )
    if not result or not result.get("accountRole"):
        print("  Could not fetch users. Skipping user ID discovery.")
        return
    roles = result.get("accountRole", {})
    users = []
    for entry in roles.values():
        uid = entry.get("userId") or entry.get("user_id")
        if not uid:
            continue
        role = entry.get("role", "")
        udata = (result.get("user") or {}).get(uid, {})
        name = udata.get("name", "")
        users.append({"id": uid, "name": name, "role": role})
    if not users:
        print("  No users found.")
        return
    if len(users) == 1:
        user = users[0]
        config.save_env_value("CODECKS_USER_ID", user["id"])
        config.USER_ID = user["id"]
        print(f"  Found user: {user['name']} ({user['role']})")
        print("  Saved to .env\n")
        return
    # Multiple users — ask which one
    print(f"  Found {len(users)} user(s):")
    for i, u in enumerate(users, 1):
        print(f"    {i}. {u['name']} ({u['role']})")
    print()
    while True:
        choice = input("  Which user are you? [1]: ").strip()
        if choice == "" or choice == "1":
            idx = 0
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(users):
                break
        except ValueError:
            pass
        print(f"  Enter a number 1-{len(users)}")
    user = users[idx]
    config.save_env_value("CODECKS_USER_ID", user["id"])
    config.USER_ID = user["id"]
    print(f"  Saved: {user['name']} ({user['role']})\n")


def _setup_gdd_optional():
    """Ask about GDD configuration."""
    print("OPTIONAL: Game Design Document")
    print("-" * 40)
    print("If you have a Google Doc with your game design, the tool can")
    print("read it and sync tasks to Codecks automatically.")
    print()
    gdd_input = input("Google Doc URL (or press Enter to skip): ").strip()
    if gdd_input:
        config.save_env_value("GDD_GOOGLE_DOC_URL", gdd_input)
        print("  Saved: GDD_GOOGLE_DOC_URL")
        print("  If your doc is private, set up Google OAuth:")
        print("    See README.md or run: py codecks_api.py gdd-auth")
    else:
        print("  Skipped. You can add this later in .env")
    print()


def _setup_done():
    """Print setup completion summary."""
    final_env = config.load_env()
    print("=" * 56)
    print("  Setup complete!")
    print("=" * 56)
    print()
    print("Your configuration:")
    print(f"  Account:       {final_env.get('CODECKS_ACCOUNT', '(not set)')}")
    tok = final_env.get("CODECKS_TOKEN", "")
    print(f"  Session token: {_mask_token(tok) if tok else '(not set)'}")
    ak = final_env.get("CODECKS_ACCESS_KEY", "")
    print(f"  Access key:    {'configured' if ak else '(not set)'}")
    rt = final_env.get("CODECKS_REPORT_TOKEN", "")
    print(f"  Report token:  {'configured' if rt else '(not set)'}")
    proj = final_env.get("CODECKS_PROJECTS", "")
    proj_count = len([p for p in proj.split(",") if "=" in p]) if proj else 0
    print(f"  Projects:      {proj_count} mapped")
    ms = final_env.get("CODECKS_MILESTONES", "")
    ms_count = len([m for m in ms.split(",") if "=" in m]) if ms else 0
    print(f"  Milestones:    {ms_count} mapped")
    gdd = final_env.get("GDD_GOOGLE_DOC_URL", "")
    print(f"  GDD doc:       {'configured' if gdd else '(not set)'}")
    print()
    print("Try it out:")
    print("  py codecks_api.py account --format table")
    print("  py codecks_api.py cards --format table")
    print()
    print("If your session token expires, run setup again:")
    print("  py codecks_api.py setup")


# ---------------------------------------------------------------------------
# Main setup entry point
# ---------------------------------------------------------------------------


def cmd_setup():
    """Interactive setup wizard. Creates or updates .env configuration."""

    print()
    print("=" * 56)
    print("  codecks-cli setup wizard")
    print("=" * 56)
    print()

    current_env = config.load_env()
    existing_account = current_env.get("CODECKS_ACCOUNT", "")
    existing_token = current_env.get("CODECKS_TOKEN", "")
    has_config = bool(existing_account and existing_token)
    full_setup = True

    # --- Returning user detection ---
    if has_config:
        print("Existing configuration found:")
        print(f"  Account:  {existing_account}")
        print(f"  Token:    {_mask_token(existing_token)}")
        print()

        config.ACCOUNT = existing_account
        config.SESSION_TOKEN = existing_token
        print("Checking if your session token still works...")
        account_result = _try_call(get_account)

        if account_result and account_result.get("account"):
            acc_data = next(iter(account_result["account"].values()), None)
            acc_name = acc_data.get("name", "?") if isinstance(acc_data, dict) else "?"
            print(f"  Token is valid! Connected to: {acc_name}")
            print()
            choice = input(
                "What would you like to do?\n"
                "  1. Refresh projects and milestones\n"
                "  2. Update session token\n"
                "  3. Run full setup from scratch\n"
                "  Choice [1]: "
            ).strip()
            if choice == "" or choice == "1":
                print()
                _setup_discover_projects()
                _setup_discover_milestones()
                _setup_discover_user()
                _setup_gdd_optional()
                _setup_done()
                return
            elif choice == "2":
                full_setup = False
                print()
                # Fall through to token prompt
            elif choice == "3":
                full_setup = True
                has_config = False
                print()
            else:
                print("Invalid choice. Running full setup.\n")
                full_setup = True
                has_config = False
        else:
            print("  Token has expired or is invalid.")
            print("  Let's get a fresh one.\n")
            full_setup = False
            # Fall through to token prompt

    # --- Step 1: Account subdomain ---
    if not has_config and full_setup:
        print("STEP 1: Account name")
        print("-" * 40)
        print("Your Codecks account subdomain is the word before .codecks.io")
        print("  Example: if you use hafu.codecks.io, enter: hafu")
        print()
        while True:
            account_input = input("Account subdomain: ").strip().lower()
            if account_input:
                if ".codecks.io" in account_input:
                    account_input = account_input.split(".codecks.io")[0]
                    if "://" in account_input:
                        account_input = account_input.split("://")[1]
                config.save_env_value("CODECKS_ACCOUNT", account_input)
                config.ACCOUNT = account_input
                print(f"  Saved: {account_input}")
                break
            print("  Account name cannot be empty. Try again.")
        print()

    # --- Step 2: Session token ---
    step = "STEP 2" if full_setup and not has_config else "Session token"
    print(f"{step}: Session token")
    print("-" * 40)
    print("This token lets the tool read your Codecks data.")
    print("It comes from your browser and expires when your session ends.")
    print()
    print("How to get it:")
    acct = config.ACCOUNT or "your-account"
    print(f"  1. Open your browser and go to {acct}.codecks.io")
    print("  2. Press F12 to open Developer Tools")
    print("  3. Click the Network tab")
    print("  4. Refresh the page (F5)")
    print("  5. Click any request to api.codecks.io")
    print("  6. In the Headers tab, find the Cookie header")
    print("  7. Copy the value after at= (a string of letters and numbers)")
    print()

    for attempt in range(3):
        token_input = input("Paste your session token: ").strip()
        if not token_input:
            print("  Token cannot be empty. Try again.")
            continue

        # Clean common paste mistakes
        if token_input.startswith("at="):
            token_input = token_input[3:]
        token_input = token_input.strip('"').strip("'").strip()

        config.save_env_value("CODECKS_TOKEN", token_input)
        config.SESSION_TOKEN = token_input

        print("  Validating...")
        account_result = _try_call(get_account)
        if account_result and account_result.get("account"):
            acc_data = next(iter(account_result["account"].values()), None)
            acc_name = acc_data.get("name", "?") if isinstance(acc_data, dict) else "?"
            print(f"  Token works! Connected to: {acc_name}")
            break
        else:
            remaining = 2 - attempt
            if remaining > 0:
                print(f"  Token did not work. {remaining} attempt(s) left.")
                print("  Make sure you copied only the value after at=")
            else:
                print("  Token did not work after 3 attempts.")
                print("  Saving it anyway — you can update later with: py codecks_api.py setup")
    print()

    # --- Step 3: Access Key (full setup only) ---
    if full_setup and not has_config:
        print("STEP 3: Access Key (for creating cards)")
        print("-" * 40)
        print("The Access Key lets the tool create new cards.")
        print("If you skip this, you can still read data but not create cards.")
        print()
        print("How to get it:")
        print(f"  1. Go to {acct}.codecks.io")
        print("  2. Click the gear icon (Settings)")
        print("  3. Go to Integrations > User Reporting")
        print("  4. Copy the Access Key value")
        print()

        access_input = input("Paste your Access Key (or press Enter to skip): ").strip()
        if access_input:
            access_input = access_input.strip('"').strip("'").strip()
            config.save_env_value("CODECKS_ACCESS_KEY", access_input)
            config.ACCESS_KEY = access_input
            print("  Saved: CODECKS_ACCESS_KEY")

            print("  Generating a Report Token...")
            result = _try_call(generate_report_token, "codecks-cli")
            if result and result.get("token"):
                config.REPORT_TOKEN = result["token"]
                print(f"  Report Token created: {_mask_token(result['token'])}")
                print("  Saved to .env")
            else:
                print("  Could not generate Report Token. Try later:")
                print("    py codecks_api.py generate-token")
        else:
            print("  Skipped. Card creation won't work until you add this.")
            print("  Re-run setup later to add it.")
        print()

    # --- Auto-discover projects, milestones, user ---
    _setup_discover_projects()
    _setup_discover_milestones()
    _setup_discover_user()

    # --- Optional GDD ---
    if full_setup and not has_config:
        _setup_gdd_optional()

    _setup_done()
