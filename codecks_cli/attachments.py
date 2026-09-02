"""Attachment validation and upload helpers for Codecks cards.

Path policy: an attachment must resolve (symlinks followed) inside an allowed
root — the project root and the current working directory, plus anything listed
in the ``CODECKS_ATTACH_ALLOW_DIRS`` environment variable — and must not match
the credential denylist below.
"""

import fnmatch
import hashlib
import mimetypes
import os
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from codecks_cli.api import raw_http_request, session_request
from codecks_cli.exceptions import CliError

#: Environment variable holding extra allowed attachment roots (os.pathsep-separated).
ALLOW_DIRS_ENV = "CODECKS_ATTACH_ALLOW_DIRS"

_SENSITIVE_FILE_PATTERNS = (
    ".env",
    ".gdd_tokens.json",
    ".gdd_cache.md",
    ".pm_claims.json",
    ".pm_store.db*",
)

#: Basename globs that never get attached, no matter which root they live under.
_DENIED_NAME_PATTERNS = (
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "*token*",
    "*secret*",
)

#: Absolute prefixes that are never attachable (pseudo-filesystems, system config).
_DENIED_ROOTS = ("/etc", "/proc", "/sys")

#: Characters that would break out of a Content-Disposition filename parameter.
_ILLEGAL_NAME_CHARS = ('"', "\r", "\n")


def _escape_header_param(value: str) -> str:
    """Escape backslashes and quotes for a quoted-string header parameter."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _reject_crlf(value: str, label: str) -> None:
    """Refuse CR/LF, which no amount of quoting makes safe in a MIME part."""
    if "\r" in value or "\n" in value:
        raise CliError(f"[ERROR] {label} contains a CR/LF character: {value!r}")


@dataclass(frozen=True)
class AttachmentFile:
    """Local file metadata needed for Codecks/S3 uploads."""

    path: Path
    file_name: str
    content_type: str
    size: int


def _skip_root(entry: str, reason: str) -> None:
    """Warn (once per call) that an allowlist entry was ignored."""
    warnings.warn(
        f"{ALLOW_DIRS_ENV} entry {entry!r} ignored: {reason}.",
        RuntimeWarning,
        stacklevel=4,
    )


def _validated_root(path: Path, source: str | None = None) -> Path | None:
    """Return *path* resolved if it is usable as an attachment root, else ``None``.

    The same checks apply to the built-in defaults and to
    ``CODECKS_ATTACH_ALLOW_DIRS`` entries: the candidate must be absolute,
    resolvable, an existing directory, and not a whole filesystem root — a
    desktop MCP client that launches the server with ``/`` as its working
    directory must not thereby make the entire disk attachable. *source* is the
    raw environment entry when the candidate came from the environment; those
    rejections warn, while a default that fails is skipped silently.
    """
    candidate = path.expanduser()
    if not candidate.is_absolute():
        if source is not None:
            _skip_root(source, "not an absolute path")
        return None
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as e:
        if source is not None:
            _skip_root(source, f"could not be resolved ({e})")
        return None
    if resolved.parent == resolved:
        if source is not None:
            _skip_root(source, "a filesystem root would allow every file on the disk")
        return None
    try:
        is_dir = resolved.is_dir()
    except OSError as e:
        if source is not None:
            _skip_root(source, f"could not be inspected ({e})")
        return None
    if not is_dir:
        if source is not None:
            _skip_root(source, "not an existing directory")
        return None
    return resolved


def _allowed_roots() -> list[Path]:
    """Directories attachments may be read from.

    Allowed by default: the project root and the current working directory —
    for a pip-installed package the project root is ``site-packages``, which
    holds nothing worth attaching, so the directory the user actually works in
    has to count too. Extra roots come from ``CODECKS_ATTACH_ALLOW_DIRS``. Every
    candidate goes through :func:`_validated_root`, so a filesystem root never
    becomes an allowed root — not from the environment, and not from a server
    started with ``/`` as its working directory either.
    """
    from codecks_cli.config import _PROJECT_ROOT

    roots: list[Path] = []

    def add(root: Path | None) -> None:
        if root is not None and root not in roots:
            roots.append(root)

    defaults: list[Path] = [Path(_PROJECT_ROOT)]
    try:
        defaults.append(Path.cwd())
    except OSError:
        pass  # Working directory was removed out from under us.
    for default in defaults:
        add(_validated_root(default))

    for entry in (os.environ.get(ALLOW_DIRS_ENV) or "").split(os.pathsep):
        entry = entry.strip()
        if not entry:
            continue
        add(_validated_root(Path(entry), source=entry))
    return roots


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _is_sensitive_name(name: str) -> bool:
    """True if a basename matches the credential/state-file denylist."""
    lowered = name.lower()
    patterns = _SENSITIVE_FILE_PATTERNS + _DENIED_NAME_PATTERNS
    return any(fnmatch.fnmatch(lowered, pattern.lower()) for pattern in patterns)


def _check_attachment_path(raw_path: str) -> Path:
    """Resolve *raw_path* and enforce the attachment path policy.

    Symlinks are followed before every check, so a ``link.txt -> ~/.ssh/id_rsa``
    rename cannot smuggle a file past the denylist or out of the allowed roots.
    Returns the fully resolved path, or raises ``CliError`` explaining the
    rejection.
    """
    try:
        resolved = Path(raw_path).expanduser().resolve(strict=False)
    except OSError as e:
        raise CliError(f"[ERROR] Attachment path could not be resolved: {raw_path} ({e})") from e

    for char, label in zip(_ILLEGAL_NAME_CHARS, ('"', "CR", "LF"), strict=True):
        if char in resolved.name:
            raise CliError(
                f"[ERROR] Attachment file name contains an illegal character ({label}): "
                f"{resolved.name!r}"
            )

    posix = resolved.as_posix()
    for denied in _DENIED_ROOTS:
        if posix == denied or posix.startswith(denied + "/"):
            raise CliError(f"[ERROR] Refusing to attach a file under {denied}: {resolved}")

    if _is_sensitive_name(resolved.name):
        raise CliError(f"[ERROR] Refusing to attach sensitive local file: {resolved.name}")

    roots = _allowed_roots()
    root = next((r for r in roots if _is_within(resolved, r)), None)
    if root is None:
        allowed = ", ".join(str(r) for r in roots) or "(none)"
        raise CliError(
            f"[ERROR] Attachment path is outside the allowed roots: {resolved}\n"
            f"  Allowed: {allowed}\n"
            f"  Add more roots via the {ALLOW_DIRS_ENV} environment variable "
            f"({os.pathsep!r}-separated absolute directories)."
        )

    # Below the allowed root, refuse any dot-prefixed component: that covers
    # .ssh/, .aws/, .env.local, .gdd_tokens.json and friends. Components *above*
    # the root are the operator's choice and are not our business.
    for part in resolved.relative_to(root).parts:
        if part.startswith("."):
            raise CliError(
                f"[ERROR] Refusing to attach a dot-prefixed path component ({part!r}): {resolved}"
            )
    return resolved


def file_sha256(path: Path) -> str:
    """Hex SHA-256 of a local file, streamed so large files stay cheap."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_attachment_files(paths: list[str]) -> list[AttachmentFile]:
    """Validate local file paths and return normalized attachment metadata."""
    if not paths:
        raise CliError("[ERROR] At least one attachment file is required.")

    files: list[AttachmentFile] = []
    seen_names: set[str] = set()
    for raw_path in paths:
        path = _check_attachment_path(raw_path)
        if not path.exists():
            raise CliError(f"[ERROR] Attachment file not found: {raw_path}")
        if not path.is_file():
            raise CliError(f"[ERROR] Attachment path is not a file: {raw_path}")
        if not os.access(path, os.R_OK):
            raise CliError(f"[ERROR] Attachment file is not readable: {raw_path}")

        file_name = path.name
        if file_name in seen_names:
            raise CliError(f"[ERROR] Duplicate attachment file name: {file_name}")
        seen_names.add(file_name)

        content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        files.append(
            AttachmentFile(
                path=path,
                file_name=file_name,
                content_type=content_type,
                size=path.stat().st_size,
            )
        )
    return files


def preview_attachment_files(paths: list[str]) -> list[dict[str, object]]:
    """Validate *paths* and describe them without uploading anything."""
    attachments = prepare_attachment_files(paths)
    return [
        {
            "path": raw_path,
            "resolved": str(a.path),
            "size": a.size,
            "sha256": file_sha256(a.path),
        }
        for raw_path, a in zip(paths, attachments, strict=True)
    ]


def build_multipart_body(
    attachment: AttachmentFile,
    fields: dict[str, object] | None,
    *,
    boundary: str | None = None,
) -> tuple[bytes, str]:
    """Build a multipart/form-data body for a single S3 file upload.

    Field names and values come from the ``/s3/sign`` response, i.e. from the
    server — they are still treated as untrusted: CR/LF is refused outright
    (it would let a crafted field inject headers or a boundary line) and the
    name is escaped like the file name before it goes into the quoted-string
    ``Content-Disposition`` parameter. Values are not escaped: they are body
    content, not header syntax, and rewriting them would corrupt the upload
    policy/signature fields.
    """
    _reject_crlf(attachment.file_name, "Attachment file name")
    boundary = boundary or f"----codecks-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add_field(name: str, value: object) -> None:
        text = str(value)
        _reject_crlf(name, "Upload field name")
        _reject_crlf(text, f"Upload field {name!r} value")
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{_escape_header_param(name)}"\r\n\r\n'.encode()
        )
        chunks.append(text.encode("utf-8"))
        chunks.append(b"\r\n")

    for key, value in (fields or {}).items():
        add_field(key, value)
    add_field("Content-Type", attachment.content_type)

    chunks.append(f"--{boundary}\r\n".encode())
    # Escape backslashes and quotes so a crafted file name cannot terminate the
    # quoted-string parameter and inject extra header fields (RFC 6266 / 2616).
    escaped_name = _escape_header_param(attachment.file_name)
    chunks.append(
        (
            'Content-Disposition: form-data; name="file"; '
            f'filename="{escaped_name}"\r\n'
            f"Content-Type: {attachment.content_type}\r\n\r\n"
        ).encode()
    )
    with attachment.path.open("rb") as f:
        chunks.append(f.read())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())

    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _upload_to_url(
    attachment: AttachmentFile,
    upload_info: dict[str, object],
    *,
    url_keys: tuple[str, ...],
) -> None:
    signed_url = next(
        (upload_info.get(key) for key in url_keys if isinstance(upload_info.get(key), str)),
        None,
    )
    if not isinstance(signed_url, str) or not signed_url:
        raise CliError(f"[ERROR] Upload URL missing for attachment '{attachment.file_name}'.")
    fields = upload_info.get("fields") or {}
    if not isinstance(fields, dict):
        raise CliError(
            f"[ERROR] Upload fields were invalid for attachment '{attachment.file_name}'."
        )
    body, content_type = build_multipart_body(attachment, fields)
    raw_http_request(signed_url, data=body, headers={"Content-Type": content_type}, method="POST")


def _upload_to_signed_url(attachment: AttachmentFile, upload_info: dict[str, object]) -> None:
    _upload_to_url(attachment, upload_info, url_keys=("signedUrl", "signed_url"))


def _file_result(attachment: AttachmentFile) -> dict[str, object]:
    return {
        "file_name": attachment.file_name,
        "size": attachment.size,
        "type": attachment.content_type,
    }


def upload_report_files(
    attachments: list[AttachmentFile],
    upload_urls: list[dict[str, object]],
) -> dict[str, object]:
    """Upload files returned by the user-report card creation endpoint."""
    if len(upload_urls) < len(attachments):
        raise CliError(
            "[ERROR] Card creation response did not include enough upload URLs "
            f"({len(upload_urls)} for {len(attachments)} file(s))."
        )

    uploaded: list[dict[str, object]] = []
    for attachment, upload_info in zip(attachments, upload_urls, strict=False):
        if not isinstance(upload_info, dict):
            raise CliError(f"[ERROR] Invalid upload info for attachment '{attachment.file_name}'.")
        _upload_to_url(attachment, upload_info, url_keys=("url", "signedUrl", "signed_url"))
        uploaded.append(_file_result(attachment))

    return {"ok": True, "attached": len(uploaded), "failed": 0, "files": uploaded}


def attach_files_to_card(
    card_id: str, paths: list[str], *, user_id: str, dry_run: bool = False
) -> dict[str, object]:
    """Upload local files and attach them to an existing Codecks card.

    With ``dry_run=True`` the paths are validated against the attachment policy
    and described (resolved path, size, sha256) but nothing is uploaded.
    """
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "card_id": card_id,
            "attached": 0,
            "failed": 0,
            "files": preview_attachment_files(paths),
        }
    attachments = prepare_attachment_files(paths)
    attached: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []

    for attachment in attachments:
        try:
            sign_path = f"/s3/sign?objectName={quote(attachment.file_name)}"
            upload_info = session_request(sign_path, method="GET", idempotent=True)
            if not isinstance(upload_info, dict):
                raise CliError(
                    f"[ERROR] Invalid signing response for attachment '{attachment.file_name}'."
                )
            _upload_to_signed_url(attachment, upload_info)
            public_url = (
                upload_info.get("url") or upload_info.get("publicUrl") or upload_info.get("fileUrl")
            )
            if not isinstance(public_url, str) or not public_url:
                raise CliError(
                    f"[ERROR] Public URL missing for attachment '{attachment.file_name}'."
                )
            session_request(
                "/dispatch/cards/addFile",
                {
                    "cardId": card_id,
                    "userId": user_id,
                    "fileData": {
                        "fileName": attachment.file_name,
                        "url": public_url,
                        "size": attachment.size,
                        "type": attachment.content_type,
                    },
                },
            )
            attached.append(_file_result(attachment))
        except CliError as e:
            failures.append({"file_name": attachment.file_name, "error": str(e)})

    if failures and not attached:
        first = failures[0]
        raise CliError(
            f"[ERROR] Failed to attach '{first['file_name']}' to card {card_id}: {first['error']}"
        )

    result: dict[str, object] = {
        "ok": not failures,
        "card_id": card_id,
        "attached": len(attached),
        "failed": len(failures),
        "files": attached,
    }
    if failures:
        result["failures"] = failures
    return result
