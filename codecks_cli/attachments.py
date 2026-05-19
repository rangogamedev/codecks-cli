"""Attachment validation and upload helpers for Codecks cards."""

import fnmatch
import mimetypes
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from codecks_cli.api import raw_http_request, session_request
from codecks_cli.exceptions import CliError

_SENSITIVE_FILE_PATTERNS = (
    ".env",
    ".gdd_tokens.json",
    ".gdd_cache.md",
    ".pm_claims.json",
    ".pm_store.db*",
)


@dataclass(frozen=True)
class AttachmentFile:
    """Local file metadata needed for Codecks/S3 uploads."""

    path: Path
    file_name: str
    content_type: str
    size: int


def _is_sensitive_file(path: Path) -> bool:
    # Resolve symlinks so a `link.txt -> .env` rename cannot bypass the basename match.
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path
    name = resolved.name.lower()
    return any(fnmatch.fnmatch(name, pattern.lower()) for pattern in _SENSITIVE_FILE_PATTERNS)


def prepare_attachment_files(paths: list[str]) -> list[AttachmentFile]:
    """Validate local file paths and return normalized attachment metadata."""
    if not paths:
        raise CliError("[ERROR] At least one attachment file is required.")

    files: list[AttachmentFile] = []
    seen_names: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise CliError(f"[ERROR] Attachment file not found: {raw_path}")
        if not path.is_file():
            raise CliError(f"[ERROR] Attachment path is not a file: {raw_path}")
        if _is_sensitive_file(path):
            raise CliError(f"[ERROR] Refusing to attach sensitive local file: {path.name}")
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


def build_multipart_body(
    attachment: AttachmentFile,
    fields: dict[str, object] | None,
    *,
    boundary: str | None = None,
) -> tuple[bytes, str]:
    """Build a multipart/form-data body for a single S3 file upload."""
    boundary = boundary or f"----codecks-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add_field(name: str, value: object) -> None:
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    for key, value in (fields or {}).items():
        add_field(key, value)
    add_field("Content-Type", attachment.content_type)

    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        (
            'Content-Disposition: form-data; name="file"; '
            f'filename="{attachment.file_name}"\r\n'
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


def attach_files_to_card(card_id: str, paths: list[str], *, user_id: str) -> dict[str, object]:
    """Upload local files and attach them to an existing Codecks card."""
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
