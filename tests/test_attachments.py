"""Tests for attachment validation, multipart upload helpers, and workflows."""

import hashlib
import os
import warnings
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from codecks_cli.exceptions import CliError


def _scratch_dir() -> Path:
    candidates = [Path(".sandbox_tmp")] if os.name == "nt" else [Path("/tmp"), Path(".sandbox_tmp")]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            path = candidate / f"codecks-attachments-{uuid4().hex}"
            path.mkdir(parents=True, exist_ok=False)
            probe = path / ".write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return path
        except OSError:
            continue
    raise RuntimeError("No writable scratch directory available for attachment tests.")


@pytest.fixture(autouse=True)
def _allow_scratch_roots(monkeypatch):
    """Scratch dirs live outside the project root — allowlist them for these tests.

    Tests that exercise the allowlist itself override this with their own
    ``monkeypatch.setenv`` / ``delenv`` call.
    """
    from codecks_cli import attachments

    roots = []
    for candidate in (Path("/tmp"), Path(".sandbox_tmp")):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        # Non-existent entries are skipped (with a warning) by the allowlist.
        if resolved.is_dir():
            roots.append(str(resolved))
    monkeypatch.setenv(attachments.ALLOW_DIRS_ENV, os.pathsep.join(roots))


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


def test_prepare_files_rejects_symlink_to_sensitive_file():
    """Sensitive-file denylist must follow symlinks so a renamed link cannot bypass."""
    from codecks_cli.attachments import prepare_attachment_files

    scratch = _scratch_dir()
    target = scratch / ".env"
    target.write_text("CODECKS_TOKEN=secret", encoding="utf-8")
    link = scratch / "innocent.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported on this platform/user")

    with pytest.raises(CliError, match="Refusing to attach sensitive local file"):
        prepare_attachment_files([str(link)])


@patch("codecks_cli.attachments.raw_http_request")
def test_upload_report_files_uses_upload_urls(mock_raw):
    from codecks_cli.attachments import prepare_attachment_files, upload_report_files

    source = _scratch_dir() / "report.txt"
    source.write_text("hello", encoding="utf-8")
    attachment = prepare_attachment_files([str(source)])[0]

    result = upload_report_files([attachment], [{"url": "https://s3.example", "fields": {}}])

    assert result["ok"] is True
    assert result["attached"] == 1
    mock_raw.assert_called_once()


# ---------------------------------------------------------------------------
# Path policy: allowlisted roots + credential denylist
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    """Point the attachment allowlist at an isolated project root only."""
    from codecks_cli import attachments, config

    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(config, "_PROJECT_ROOT", str(root))
    # The current directory is an allowed root too, so point it at the same
    # isolated tree — otherwise the repo checkout would widen the policy.
    monkeypatch.chdir(root)
    monkeypatch.delenv(attachments.ALLOW_DIRS_ENV, raising=False)
    return root


def test_file_inside_project_root_is_accepted(project_root):
    from codecks_cli.attachments import prepare_attachment_files

    target = project_root / "assets" / "mockup.png"
    target.parent.mkdir()
    target.write_bytes(b"png")

    files = prepare_attachment_files([str(target)])

    assert len(files) == 1
    assert files[0].file_name == "mockup.png"


def test_file_outside_project_root_is_rejected(project_root, tmp_path):
    from codecks_cli.attachments import ALLOW_DIRS_ENV, prepare_attachment_files

    outside = tmp_path / "elsewhere" / "notes.txt"
    outside.parent.mkdir()
    outside.write_text("data", encoding="utf-8")

    with pytest.raises(CliError) as exc:
        prepare_attachment_files([str(outside)])
    assert "outside the allowed roots" in str(exc.value)
    assert ALLOW_DIRS_ENV in str(exc.value)


def test_env_override_allows_extra_root(project_root, tmp_path, monkeypatch):
    from codecks_cli.attachments import ALLOW_DIRS_ENV, prepare_attachment_files

    outside = tmp_path / "shared" / "notes.txt"
    outside.parent.mkdir()
    outside.write_text("data", encoding="utf-8")
    monkeypatch.setenv(
        ALLOW_DIRS_ENV, os.pathsep.join([str(tmp_path / "unused"), str(outside.parent)])
    )

    # The bogus first entry is skipped with a warning; the valid one still applies.
    with pytest.warns(RuntimeWarning, match="not an existing directory"):
        files = prepare_attachment_files([str(outside)])

    assert files[0].file_name == "notes.txt"


def test_dotfile_component_is_rejected(project_root):
    from codecks_cli.attachments import prepare_attachment_files

    target = project_root / ".ssh" / "config"
    target.parent.mkdir()
    target.write_text("Host *", encoding="utf-8")

    with pytest.raises(CliError, match="dot-prefixed path component"):
        prepare_attachment_files([str(target)])


@pytest.mark.parametrize(
    "name", ["server.pem", "deploy.key", "id_rsa", "id_ed25519.pub", "API_TOKEN.txt", "Secrets.md"]
)
def test_credential_looking_names_are_rejected(project_root, name):
    from codecks_cli.attachments import prepare_attachment_files

    target = project_root / name
    target.write_text("x", encoding="utf-8")

    with pytest.raises(CliError, match="Refusing to attach sensitive local file"):
        prepare_attachment_files([str(target)])


@pytest.mark.parametrize("bad", ['quote".txt', "carriage\rreturn.txt", "line\nfeed.txt"])
def test_illegal_filename_characters_are_rejected(project_root, bad):
    from codecks_cli.attachments import prepare_attachment_files

    target = project_root / bad
    try:
        target.write_text("x", encoding="utf-8")
    except OSError:
        pytest.skip("Filesystem rejects this file name")

    with pytest.raises(CliError, match="illegal character"):
        prepare_attachment_files([str(target)])


def test_symlink_escaping_the_root_is_rejected(project_root, tmp_path):
    from codecks_cli.attachments import prepare_attachment_files

    outside = tmp_path / "outside.txt"
    outside.write_text("data", encoding="utf-8")
    link = project_root / "innocent.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported on this platform/user")

    with pytest.raises(CliError, match="outside the allowed roots"):
        prepare_attachment_files([str(link)])


def test_multipart_escapes_quotes_and_backslashes_in_filename(project_root):
    from codecks_cli.attachments import AttachmentFile, build_multipart_body

    target = project_root / "plain.txt"
    target.write_text("body", encoding="utf-8")
    attachment = AttachmentFile(
        path=target,
        file_name='we"ird\\name.txt',
        content_type="text/plain",
        size=4,
    )

    body, _ = build_multipart_body(attachment, None, boundary="B")

    assert b'filename="we\\"ird\\\\name.txt"' in body


def test_dry_run_previews_without_uploading(project_root):
    from codecks_cli.attachments import attach_files_to_card

    target = project_root / "mockup.png"
    target.write_bytes(b"png")

    with (
        patch("codecks_cli.attachments.session_request") as mock_session,
        patch("codecks_cli.attachments.raw_http_request") as mock_raw,
    ):
        result = attach_files_to_card("card-1", [str(target)], user_id="u1", dry_run=True)

    mock_session.assert_not_called()
    mock_raw.assert_not_called()
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["attached"] == 0
    entry = result["files"][0]
    assert entry["path"] == str(target)
    assert entry["resolved"] == str(target)
    assert entry["size"] == 3
    assert entry["sha256"] == hashlib.sha256(b"png").hexdigest()


def test_dry_run_still_enforces_the_path_policy(project_root, tmp_path):
    from codecks_cli.attachments import attach_files_to_card

    outside = tmp_path / "outside.txt"
    outside.write_text("data", encoding="utf-8")

    with pytest.raises(CliError, match="outside the allowed roots"):
        attach_files_to_card("card-1", [str(outside)], user_id="u1", dry_run=True)


def test_client_dry_run_does_not_resolve_a_user_id(project_root):
    from codecks_cli.client import CodecksClient

    target = project_root / "mockup.png"
    target.write_bytes(b"png")

    with (
        patch("codecks_cli.client._get_user_id") as mock_user,
        patch("codecks_cli.attachments.session_request") as mock_session,
    ):
        client = CodecksClient(validate_token=False)
        result = client.attach_files("card-1", [str(target)], dry_run=True)

    mock_user.assert_not_called()
    mock_session.assert_not_called()
    assert result["dry_run"] is True


# ---------------------------------------------------------------------------
# Allowed-root validation
# ---------------------------------------------------------------------------


def test_current_directory_is_an_allowed_root_by_default(tmp_path, monkeypatch):
    """pip installs put _PROJECT_ROOT in site-packages, so cwd has to count too."""
    from codecks_cli import attachments, config

    elsewhere = tmp_path / "site-packages"
    elsewhere.mkdir()
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.setattr(config, "_PROJECT_ROOT", str(elsewhere))
    monkeypatch.delenv(attachments.ALLOW_DIRS_ENV, raising=False)
    monkeypatch.chdir(workdir)

    target = workdir / "hero.png"
    target.write_bytes(b"png")

    files = attachments.prepare_attachment_files([str(target)])

    assert files[0].file_name == "hero.png"
    assert workdir.resolve() in attachments._allowed_roots()


def test_filesystem_root_entry_is_skipped_with_a_warning(project_root, monkeypatch):
    from codecks_cli.attachments import ALLOW_DIRS_ENV, _allowed_roots

    fs_root = str(Path(project_root.anchor or "/"))
    monkeypatch.setenv(ALLOW_DIRS_ENV, fs_root)

    with pytest.warns(RuntimeWarning, match="filesystem root"):
        roots = _allowed_roots()

    assert Path(fs_root).resolve() not in roots


def test_relative_entry_is_skipped_with_a_warning(project_root, monkeypatch):
    from codecks_cli.attachments import ALLOW_DIRS_ENV, _allowed_roots

    monkeypatch.setenv(ALLOW_DIRS_ENV, ".")

    with pytest.warns(RuntimeWarning, match="not an absolute path"):
        roots = _allowed_roots()

    # Only the two defaults (project root and cwd, which the fixture makes equal).
    assert roots == [project_root.resolve()]


def test_nonexistent_entry_is_skipped_with_a_warning(project_root, tmp_path, monkeypatch):
    from codecks_cli.attachments import ALLOW_DIRS_ENV, _allowed_roots

    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv(ALLOW_DIRS_ENV, str(missing))

    with pytest.warns(RuntimeWarning, match="not an existing directory"):
        roots = _allowed_roots()

    assert missing.resolve() not in roots


def test_file_entry_is_skipped_with_a_warning(project_root, tmp_path, monkeypatch):
    from codecks_cli.attachments import ALLOW_DIRS_ENV, _allowed_roots

    a_file = tmp_path / "not-a-dir.txt"
    a_file.write_text("x", encoding="utf-8")
    monkeypatch.setenv(ALLOW_DIRS_ENV, str(a_file))

    with pytest.warns(RuntimeWarning, match="not an existing directory"):
        roots = _allowed_roots()

    assert a_file.resolve() not in roots


def test_valid_entry_is_kept_alongside_the_defaults(project_root, tmp_path, monkeypatch):
    from codecks_cli.attachments import ALLOW_DIRS_ENV, _allowed_roots

    extra = tmp_path / "shared"
    extra.mkdir()
    monkeypatch.setenv(ALLOW_DIRS_ENV, str(extra))

    roots = _allowed_roots()

    assert extra.resolve() in roots
    assert project_root.resolve() in roots


def test_filesystem_root_cwd_is_not_an_allowed_root(project_root, monkeypatch):
    """A client launching the server with cwd ``/`` must not open the whole disk."""
    from codecks_cli.attachments import _allowed_roots

    fs_root = Path(project_root.anchor or "/")
    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: fs_root))

    with warnings.catch_warnings():
        # A rejected *default* root is skipped silently — no warning spam.
        warnings.simplefilter("error")
        roots = _allowed_roots()

    assert fs_root.resolve() not in roots
    assert roots == [project_root.resolve()]


def test_normal_cwd_is_an_allowed_root(project_root, tmp_path, monkeypatch):
    """An ordinary working directory still counts as a default root."""
    from codecks_cli.attachments import _allowed_roots

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    roots = _allowed_roots()

    assert workdir.resolve() in roots
    assert project_root.resolve() in roots


# ---------------------------------------------------------------------------
# Multipart field hardening (fields come from the /s3/sign server response)
# ---------------------------------------------------------------------------


def _plain_attachment(project_root):
    from codecks_cli.attachments import AttachmentFile

    target = project_root / "plain.txt"
    target.write_text("body", encoding="utf-8")
    return AttachmentFile(path=target, file_name="plain.txt", content_type="text/plain", size=4)


def test_multipart_rejects_crlf_in_a_field_name(project_root):
    from codecks_cli.attachments import build_multipart_body

    attachment = _plain_attachment(project_root)

    with pytest.raises(CliError, match="Upload field name contains a CR/LF"):
        build_multipart_body(attachment, {"key\r\nX-Injected": "v"}, boundary="B")


def test_multipart_rejects_crlf_in_a_field_value(project_root):
    from codecks_cli.attachments import build_multipart_body

    attachment = _plain_attachment(project_root)

    with pytest.raises(CliError, match="value contains a CR/LF"):
        build_multipart_body(attachment, {"policy": "v\r\n--B\r\n"}, boundary="B")


def test_multipart_escapes_quotes_and_backslashes_in_a_field_name(project_root):
    from codecks_cli.attachments import build_multipart_body

    attachment = _plain_attachment(project_root)

    body, _ = build_multipart_body(attachment, {'we"ird\\key': "value"}, boundary="B")

    assert b'name="we\\"ird\\\\key"' in body
    assert b"value" in body


def test_multipart_leaves_field_values_verbatim(project_root):
    """Values are body content: escaping them would corrupt the S3 policy fields."""
    from codecks_cli.attachments import build_multipart_body

    attachment = _plain_attachment(project_root)

    body, _ = build_multipart_body(attachment, {"policy": 'a"b\\c'}, boundary="B")

    assert b'a"b\\c' in body


def test_multipart_rejects_crlf_in_the_file_name(project_root):
    from codecks_cli.attachments import AttachmentFile, build_multipart_body

    target = project_root / "plain.txt"
    target.write_text("body", encoding="utf-8")
    attachment = AttachmentFile(
        path=target,
        file_name="evil\r\nContent-Type: text/html",
        content_type="text/plain",
        size=4,
    )

    with pytest.raises(CliError, match="Attachment file name contains a CR/LF"):
        build_multipart_body(attachment, None, boundary="B")
