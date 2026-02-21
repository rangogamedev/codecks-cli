"""Low-level table rendering helpers (stdlib only)."""

import re

_CONTROL_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _trunc(s, maxlen):
    """Truncate string with ellipsis indicator."""
    if not s:
        return ""
    return s[: maxlen - 1] + "\u2026" if len(s) > maxlen else s


def _sanitize_str(s):
    """Strip ANSI escape sequences and control chars from table output.
    Preserves newlines (\\n) and tabs (\\t)."""
    if not s:
        return s
    return _CONTROL_RE.sub("", str(s))


def _table(columns, rows, footer=None):
    """Build a formatted table string.
    columns: list of (name, width) tuples. Last column has no width (fills).
    rows: list of tuples matching columns.
    footer: optional footer line."""
    # Header
    parts = []
    for i, (name, width) in enumerate(columns):
        if i == len(columns) - 1:
            parts.append(name)
        else:
            parts.append(f"{name:<{width}}")
    header = " ".join(parts)
    sep = "-" * max(len(header), 90)
    # Rows
    lines = [header, sep]
    for row in rows:
        parts = []
        for i, val in enumerate(row):
            safe = _sanitize_str(val) if isinstance(val, str) else str(val)
            if i == len(columns) - 1:
                parts.append(safe)
            else:
                parts.append(f"{safe:<{columns[i][1]}}")
        lines.append(" ".join(parts))
    if footer:
        lines.append(f"\n{footer}")
    return "\n".join(lines)
