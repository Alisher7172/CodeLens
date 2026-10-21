# tests/test_safety.py
from pathlib import Path
import pytest
from ingestion.models import SkipReason
from ingestion.safety import FileSafetyChecker


def test_max_file_size_threshold(tmp_path: Path):
    checker = FileSafetyChecker(root_dir=tmp_path, max_file_size_bytes=100)

    small_file = tmp_path / "small.txt"
    small_file.write_text("a" * 50, encoding="utf-8")

    large_file = tmp_path / "large.txt"
    large_file.write_text("a" * 150, encoding="utf-8")

    is_safe, reason, _, size = checker.evaluate_file(small_file)
    assert is_safe is True
    assert reason is None
    assert size == 50

    is_safe, reason, detail, size = checker.evaluate_file(large_file)
    assert is_safe is False
    assert reason == SkipReason.FILE_TOO_LARGE
    assert "exceeds limit" in detail
    assert size == 150


def test_binary_file_detection(tmp_path: Path):
    checker = FileSafetyChecker(root_dir=tmp_path)

    text_file = tmp_path / "code.py"
    text_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    binary_file = tmp_path / "data.bin"
    # Null byte signature
    binary_file.write_bytes(b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00")

    is_safe_text, reason_text, _, _ = checker.evaluate_file(text_file)
    assert is_safe_text is True
    assert reason_text is None

    is_safe_bin, reason_bin, _, _ = checker.evaluate_file(binary_file)
    assert is_safe_bin is False
    assert reason_bin == SkipReason.BINARY_FILE


def test_symlink_traversal_prevention(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    secret_file = outside_dir / "secret.env"
    secret_file.write_text("SECRET=123", encoding="utf-8")

    # Internal file
    internal_file = repo_dir / "internal.py"
    internal_file.write_text("print(1)", encoding="utf-8")

    # Safe internal symlink
    safe_link = repo_dir / "safe_link.py"
    try:
        safe_link.symlink_to(internal_file)
        has_symlink_support = True
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation requires elevated permissions on this system")

    # Escaping symlink pointing outside repo
    escaping_link = repo_dir / "escape_link.env"
    escaping_link.symlink_to(secret_file)

    checker = FileSafetyChecker(root_dir=repo_dir)

    is_safe_internal, _, _, _ = checker.evaluate_file(safe_link)
    assert is_safe_internal is True

    is_safe_escape, reason_escape, detail_escape, _ = checker.evaluate_file(escaping_link)
    assert is_safe_escape is False
    assert reason_escape == SkipReason.IGNORED_BY_RULE
    assert "Symlink escapes repository root" in detail_escape