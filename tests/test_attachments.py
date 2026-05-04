"""Tests for attachment validation, multipart upload helpers, and workflows."""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from codecks_cli.exceptions import CliError


def _scratch_dir() -> Path:
    path = Path(".sandbox_tmp") / f"attachments-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def test_prepare_files_rejects_duplicate_basenames():
    from codecks_cli.attachments import prepare_attachment_files

    scratch = _scratch_dir()
    first = scratch / "a" / "same.txt"
    second = scratch / "b" / "same.txt"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")

    with pytest.raises(CliError, match="Duplicate attachment file name"):
        prepare_attachment_files([str(first), str(second)])


def test_prepare_files_rejects_secret_cache_files():
    from codecks_cli.attachments import prepare_attachment_files

    secret = _scratch_dir() / ".env"
    secret.write_text("CODECKS_TOKEN=secret", encoding="utf-8")

    with pytest.raises(CliError, match="Refusing to attach sensitive local file"):
        prepare_attachment_files([str(secret)])


def test_prepare_files_rejects_missing_directory_and_unreadable():
    from codecks_cli import attachments
    from codecks_cli.attachments import prepare_attachment_files

    scratch = _scratch_dir()
    missing = scratch / "missing.txt"
    directory = scratch / "folder"
    unreadable = scratch / "locked.txt"
    directory.mkdir()
    unreadable.write_text("hidden", encoding="utf-8")

    with pytest.raises(CliError, match="Attachment file not found"):
        prepare_attachment_files([str(missing)])
    with pytest.raises(CliError, match="Attachment path is not a file"):
        prepare_attachment_files([str(directory)])
    with patch.object(attachments.os, "access", return_value=False):
        with pytest.raises(CliError, match="Attachment file is not readable"):
            prepare_attachment_files([str(unreadable)])


def test_prepare_files_infers_mime_and_falls_back():
    from codecks_cli.attachments import prepare_attachment_files

    scratch = _scratch_dir()
    text_file = scratch / "note.txt"
    unknown_file = scratch / "blob.unknownextension"
    text_file.write_text("hello", encoding="utf-8")
    unknown_file.write_bytes(b"\x00\x01")

    files = prepare_attachment_files([str(text_file), str(unknown_file)])

    assert files[0].file_name == "note.txt"
    assert files[0].content_type == "text/plain"
    assert files[0].size == 5
    assert files[1].content_type == "application/octet-stream"


def test_build_multipart_body_includes_fields_content_type_and_binary():
    from codecks_cli.attachments import build_multipart_body, prepare_attachment_files

    image = _scratch_dir() / "pixel.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nbinary")
    attachment = prepare_attachment_files([str(image)])[0]

    body, content_type = build_multipart_body(
        attachment,
        fields={"key": "uploads/pixel.png", "policy": "signed"},
        boundary="test-boundary",
    )

    assert content_type == "multipart/form-data; boundary=test-boundary"
    assert b'name="key"\r\n\r\nuploads/pixel.png' in body
    assert b'name="policy"\r\n\r\nsigned' in body
    assert b'name="Content-Type"\r\n\r\nimage/png' in body
    assert b'name="file"; filename="pixel.png"' in body
    assert b"\x89PNG\r\n\x1a\nbinary" in body
    assert body.endswith(b"--test-boundary--\r\n")


@patch("codecks_cli.attachments.session_request")
@patch("codecks_cli.attachments.raw_http_request")
def test_attach_files_signs_uploads_and_dispatches_add_file(mock_raw, mock_session):
    from codecks_cli.attachments import attach_files_to_card

    source = _scratch_dir() / "concept.txt"
    source.write_text("ship it", encoding="utf-8")
    mock_session.side_effect = [
        {
            "signedUrl": "https://s3.example/upload",
            "fields": {"key": "k"},
            "url": "https://cdn.example/concept.txt",
        },
        {"ok": True},
    ]
    mock_raw.return_value = b""

    result = attach_files_to_card("card-1", [str(source)], user_id="user-1")

    assert result["ok"] is True
    assert result["card_id"] == "card-1"
    assert result["attached"] == 1
    assert result["failed"] == 0
    assert result["files"][0]["file_name"] == "concept.txt"
    assert result["files"][0]["size"] == 7
    assert result["files"][0]["type"] == "text/plain"
    assert mock_session.call_args_list[0].args[0].startswith("/s3/sign?objectName=concept.txt")
    add_payload = mock_session.call_args_list[1].args[1]
    assert add_payload == {
        "cardId": "card-1",
        "userId": "user-1",
        "fileData": {
            "fileName": "concept.txt",
            "url": "https://cdn.example/concept.txt",
            "size": 7,
            "type": "text/plain",
        },
    }


@patch("codecks_cli.attachments.session_request")
@patch("codecks_cli.attachments.raw_http_request")
def test_attach_files_reports_partial_failure_with_context(mock_raw, mock_session):
    from codecks_cli.attachments import attach_files_to_card

    scratch = _scratch_dir()
    first = scratch / "good.txt"
    second = scratch / "bad.txt"
    first.write_text("ok", encoding="utf-8")
    second.write_text("no", encoding="utf-8")
    mock_session.side_effect = [
        {
            "signedUrl": "https://s3.example/good",
            "fields": {"key": "good"},
            "url": "https://cdn.example/good.txt",
        },
        {"ok": True},
        {
            "signedUrl": "https://s3.example/bad",
            "fields": {"key": "bad"},
            "url": "https://cdn.example/bad.txt",
        },
    ]
    mock_raw.side_effect = [b"", CliError("[ERROR] upload denied")]

    result = attach_files_to_card("card-1", [str(first), str(second)], user_id="user-1")

    assert result["ok"] is False
    assert result["attached"] == 1
    assert result["failed"] == 1
    assert result["failures"][0]["file_name"] == "bad.txt"
    assert "upload denied" in result["failures"][0]["error"]


@patch("codecks_cli.attachments.raw_http_request")
def test_upload_report_files_uses_upload_urls(mock_raw):
    from codecks_cli.attachments import prepare_attachment_files, upload_report_files

    source = _scratch_dir() / "report.txt"
    source.write_text("hello", encoding="utf-8")
    attachment = prepare_attachment_files([str(source)])[0]

    result = upload_report_files([attachment], [{"signedUrl": "https://s3.example", "fields": {}}])

    assert result["ok"] is True
    assert result["attached"] == 1
    mock_raw.assert_called_once()
