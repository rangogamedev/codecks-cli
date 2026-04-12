"""Headless Playwright admin operations for Codecks.

Performs admin actions (create project/deck/milestone/tag, archive deck) via
headless Chromium. Intercepts network traffic to discover dispatch endpoints
and cache them for future direct API use.

Requires: pip install playwright && playwright install chromium
"""

import json
import os
from typing import Any

from codecks_cli import config, endpoint_cache
from codecks_cli.exceptions import CliError


def _load_selectors() -> dict:
    """Load UI selectors from the JSON config file."""
    selectors_path = os.path.join(os.path.dirname(__file__), "playwright_selectors.json")
    try:
        with open(selectors_path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise CliError(f"[ERROR] Failed to load playwright_selectors.json: {e}") from e


def _check_playwright_available() -> None:
    """Verify Playwright is installed and usable."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        raise CliError(
            "[ERROR] Playwright is not installed. "
            "Run: pip install playwright && playwright install chromium"
        ) from None


class PlaywrightAdmin:
    """Headless Codecks admin operations via Playwright.

    Authenticates using CODECKS_TOKEN cookie injection.
    Intercepts network traffic to discover/cache dispatch endpoints.
    """

    def __init__(self, headless: bool = True):
        _check_playwright_available()
        self._headless = headless
        self._selectors = _load_selectors()
        self._base_url = self._selectors.get("base_url", "https://open.codecks.io")
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._captured_requests: list[dict] = []

    def __enter__(self):
        self._start()
        return self

    def __exit__(self, *args):
        self.close()

    def _start(self) -> None:
        """Launch browser, create context with auth cookie, set up capture."""
        from playwright.sync_api import sync_playwright

        if not config.SESSION_TOKEN:
            raise CliError("[ERROR] CODECKS_TOKEN not set. Cannot authenticate with Codecks.")

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context()

        # Inject auth cookie
        self._context.add_cookies(
            [
                {
                    "name": "at",
                    "value": config.SESSION_TOKEN,
                    "domain": ".codecks.io",
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ]
        )

        self._page = self._context.new_page()
        self._page.set_default_timeout(15000)

        # Network interception for endpoint discovery
        self._page.on("request", self._on_request)

    def _on_request(self, request) -> None:
        """Capture dispatch requests for endpoint cache."""
        url = request.url
        if "/dispatch/" in url:
            try:
                payload = request.post_data_json
            except Exception:
                payload = None
            self._captured_requests.append(
                {
                    "url": url,
                    "method": request.method,
                    "payload": payload,
                }
            )

    def _save_captured_endpoint(self, operation: str) -> None:
        """Save the most recently captured dispatch endpoint to cache."""
        if not self._captured_requests:
            return
        last = self._captured_requests[-1]
        # Extract path from full URL
        url = last["url"]
        # Strip base URL to get dispatch path
        for prefix in ("https://api.codecks.io", "https://open.codecks.io"):
            if url.startswith(prefix):
                url = url[len(prefix) :]
                break
        payload_template = {}
        if last.get("payload") and isinstance(last["payload"], dict):
            # Create template with placeholder values
            payload_template = {k: f"{{{{{k}}}}}" for k in last["payload"].keys()}
        endpoint_cache.save_endpoint(
            operation=operation,
            endpoint=url,
            method=last.get("method", "POST"),
            payload_template=payload_template,
        )

    def _navigate_to_account(self) -> None:
        """Navigate to Codecks account page and wait for load."""
        self._page.goto(
            f"{self._base_url}/{config.ACCOUNT}",
            wait_until="networkidle",
        )
        # Verify we're logged in by checking for common UI elements
        try:
            self._page.wait_for_selector("[data-testid], nav, .sidebar", timeout=10000)
        except Exception:
            # Page loaded but no expected elements — might still be OK
            pass

    def create_project(self, name: str) -> dict[str, Any]:
        """Create a new project via the web UI.

        Args:
            name: Project name.

        Returns:
            Dict with ok, project_name, and source.
        """
        self._captured_requests.clear()
        self._navigate_to_account()

        sel = self._selectors.get("create_project", {})
        try:
            # Look for settings/admin area
            settings = self._page.locator(sel.get("settings_menu", "text=Settings"))
            settings.first.click()
            self._page.wait_for_timeout(1000)

            # Click "New project"
            new_btn = self._page.locator(sel.get("new_project_button", "text=New project"))
            new_btn.first.click()
            self._page.wait_for_timeout(500)

            # Fill name
            name_input = self._page.locator(sel.get("project_name_input", "role=textbox"))
            name_input.first.fill(name)

            # Submit
            submit = self._page.locator(sel.get("submit_button", "role=button[name=/create/i]"))
            submit.first.click()
            self._page.wait_for_timeout(2000)

            self._save_captured_endpoint("create_project")
            return {"ok": True, "project_name": name, "source": "playwright"}

        except Exception as e:
            return {"ok": False, "error": f"Playwright create_project failed: {e}"}

    def create_deck(self, project_name: str, deck_name: str) -> dict[str, Any]:
        """Create a new deck in a project via the web UI.

        Args:
            project_name: Project to create the deck in.
            deck_name: Name for the new deck.

        Returns:
            Dict with ok, deck_name, project_name, and source.
        """
        self._captured_requests.clear()
        self._navigate_to_account()

        sel = self._selectors.get("create_deck", {})
        try:
            # Navigate to project settings > decks
            settings = self._page.locator(sel.get("project_settings", "text=Project settings"))
            settings.first.click()
            self._page.wait_for_timeout(1000)

            decks_sec = self._page.locator(sel.get("decks_section", "text=Decks"))
            decks_sec.first.click()
            self._page.wait_for_timeout(500)

            # Click "New deck"
            new_btn = self._page.locator(sel.get("new_deck_button", "text=New deck"))
            new_btn.first.click()
            self._page.wait_for_timeout(500)

            # Fill name
            name_input = self._page.locator(sel.get("deck_name_input", "role=textbox"))
            name_input.first.fill(deck_name)

            # Submit
            submit = self._page.locator(sel.get("submit_button", "role=button[name=/create/i]"))
            submit.first.click()
            self._page.wait_for_timeout(2000)

            self._save_captured_endpoint("create_deck")
            return {
                "ok": True,
                "deck_name": deck_name,
                "project_name": project_name,
                "source": "playwright",
            }

        except Exception as e:
            return {"ok": False, "error": f"Playwright create_deck failed: {e}"}

    def create_milestone(self, name: str, target_date: str | None = None) -> dict[str, Any]:
        """Create a new milestone via the web UI.

        Args:
            name: Milestone name.
            target_date: Optional target date (YYYY-MM-DD or YYYY-MM).

        Returns:
            Dict with ok, milestone_name, and source.
        """
        self._captured_requests.clear()
        self._navigate_to_account()

        sel = self._selectors.get("create_milestone", {})
        try:
            # Navigate to milestones
            ms_link = self._page.locator(sel.get("milestones_link", "text=Milestones"))
            ms_link.first.click()
            self._page.wait_for_timeout(1000)

            # Click "New milestone"
            new_btn = self._page.locator(sel.get("new_milestone_button", "text=New milestone"))
            new_btn.first.click()
            self._page.wait_for_timeout(500)

            # Fill name
            name_input = self._page.locator(sel.get("milestone_name_input", "role=textbox"))
            name_input.first.fill(name)

            # Optional date
            if target_date:
                date_input = self._page.locator(sel.get("date_input", "input[type=date]"))
                if date_input.count() > 0:
                    date_input.first.fill(target_date)

            # Submit
            submit = self._page.locator(sel.get("submit_button", "role=button[name=/create/i]"))
            submit.first.click()
            self._page.wait_for_timeout(2000)

            self._save_captured_endpoint("create_milestone")
            return {"ok": True, "milestone_name": name, "source": "playwright"}

        except Exception as e:
            return {"ok": False, "error": f"Playwright create_milestone failed: {e}"}

    def create_tag(self, name: str, color: str | None = None) -> dict[str, Any]:
        """Create a new tag via the web UI.

        Args:
            name: Tag name.
            color: Optional hex color (e.g. "#ff0000").

        Returns:
            Dict with ok, tag_name, and source.
        """
        self._captured_requests.clear()
        self._navigate_to_account()

        sel = self._selectors.get("create_tag", {})
        try:
            # Navigate to settings > tags
            settings = self._page.locator(sel.get("settings_menu", "text=Settings"))
            settings.first.click()
            self._page.wait_for_timeout(1000)

            tags_sec = self._page.locator(sel.get("tags_section", "text=Tags"))
            tags_sec.first.click()
            self._page.wait_for_timeout(500)

            # Click "New tag"
            new_btn = self._page.locator(sel.get("new_tag_button", "text=New tag"))
            new_btn.first.click()
            self._page.wait_for_timeout(500)

            # Fill name
            name_input = self._page.locator(sel.get("tag_name_input", "role=textbox"))
            name_input.first.fill(name)

            # Optional color
            if color:
                color_input = self._page.locator(sel.get("color_input", "input[type=color]"))
                if color_input.count() > 0:
                    color_input.first.fill(color)

            # Submit
            submit = self._page.locator(sel.get("submit_button", "role=button[name=/create/i]"))
            submit.first.click()
            self._page.wait_for_timeout(2000)

            self._save_captured_endpoint("create_tag")
            return {"ok": True, "tag_name": name, "source": "playwright"}

        except Exception as e:
            return {"ok": False, "error": f"Playwright create_tag failed: {e}"}

    def archive_deck(self, deck_name: str) -> dict[str, Any]:
        """Archive a deck via the web UI.

        Args:
            deck_name: Name of the deck to archive.

        Returns:
            Dict with ok, deck_name, and source.
        """
        self._captured_requests.clear()
        self._navigate_to_account()

        sel = self._selectors.get("archive_deck", {})
        try:
            # Find the deck by name and open its context menu
            deck_el = self._page.locator(f"text={deck_name}")
            deck_el.first.click(button="right")
            self._page.wait_for_timeout(500)

            # Click archive option
            archive = self._page.locator(sel.get("archive_option", "text=Archive"))
            archive.first.click()
            self._page.wait_for_timeout(500)

            # Confirm if dialog appears
            confirm = self._page.locator(
                sel.get("confirm_button", "role=button[name=/confirm|archive/i]")
            )
            if confirm.count() > 0:
                confirm.first.click()
            self._page.wait_for_timeout(2000)

            self._save_captured_endpoint("archive_deck")
            return {"ok": True, "deck_name": deck_name, "source": "playwright"}

        except Exception as e:
            return {"ok": False, "error": f"Playwright archive_deck failed: {e}"}

    def close(self) -> None:
        """Clean up browser resources."""
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
