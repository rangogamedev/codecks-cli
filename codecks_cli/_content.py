"""Content parsing helpers for Codecks card format.

Codecks stores card title as the first line of the ``content`` field:
``"My Title\\nBody text here"``. This module provides deterministic
parsing and serialization so title/body logic has a single source of truth.
"""


def parse_content(content: str | None) -> tuple[str, str]:
    """Split content into (title, body).

    Title is the first line. Body is everything after the first ``\\n``.
    Returns ``("", "")`` for ``None`` or empty string.
    Strips ``\\r`` from line endings for Windows safety.
    """
    if not content:
        return ("", "")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    parts = content.split("\n", 1)
    title = parts[0]
    body = parts[1].lstrip("\n") if len(parts) > 1 else ""
    return (title, body)


def serialize_content(title: str, body: str) -> str:
    """Combine title and body into Codecks content format.

    Uses ``\\n\\n`` separator (blank line) so the title renders as a heading
    in the Codecks web UI. Returns empty string if both are empty.
    Returns title alone (no trailing newline) if body is empty.
    """
    if not title and not body:
        return ""
    if not body:
        return title
    return title + "\n\n" + body


def replace_body(content: str | None, new_body: str) -> str:
    """Keep existing title, replace body."""
    title, _ = parse_content(content)
    return serialize_content(title, new_body)


def replace_title(content: str | None, new_title: str) -> str:
    """Keep existing body, replace title."""
    _, body = parse_content(content)
    return serialize_content(new_title, body)


def has_title(content: str | None) -> bool:
    """Return True if content has a non-empty first line."""
    if not content:
        return False
    first_line = content.split("\n", 1)[0]
    return len(first_line.strip()) > 0
