# src/ingestion/safety.py
import os
from pathlib import Path
from ingestion.models import SkipReason

DEFAULT_MAX_FILE_SIZE_BYTES = 500 * 1024  # 500 KB
BINARY_CHECK_BUFFER_SIZE = 1024  # 1 KB chunk to detect binary content


class FileSafetyChecker:
    """Performs pre-read validation to ensure files are safe and readable."""

    def __init__(
            self,
            root_dir: Path,
            max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> None:
        self.root_dir = root_dir.resolve()
        self.max_file_size_bytes = max_file_size_bytes

    def is_symlink_safe(self, target_path: Path) -> bool:
        """
        Ensures symlinks do not escape the designated repository root.
        Returns True if the file resolves strictly inside root_dir, False otherwise.
        """
        try:
            resolved = target_path.resolve(strict=True)
            # is_relative_to is standard in Python 3.9+
            return resolved.is_relative_to(self.root_dir)
        except (OSError, ValueError):
            return False

    def is_file_too_large(self, file_path: Path) -> tuple[bool, int]:
        """
        Inspects file metadata without reading content into memory.
        Returns (is_too_large, size_in_bytes).
        """
        try:
            size = file_path.stat().st_size
            return size > self.max_file_size_bytes, size
        except OSError:
            return False, 0

    @staticmethod
    def is_binary_file(file_path: Path, sample_size: int = BINARY_CHECK_BUFFER_SIZE) -> bool:
        """
        Detects binary files by inspecting only the initial bytes.
        Checks for null bytes (b'\\x00') and UTF-8 decodability.
        """
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(sample_size)

            if not chunk:
                return False  # Empty files are valid text files

            # Null byte is the most reliable binary heuristic
            if b"\x00" in chunk:
                return True

            # Attempt decoding; decode with 'strict' except for potential trailing multi-byte splits
            try:
                chunk.decode("utf-8")
                return False
            except UnicodeDecodeError:
                # If the cut happened mid-UTF8 sequence at the end of the buffer, test with errors='ignore'
                # but verify high ratio of non-ASCII control characters
                text_characters = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
                non_text = chunk.translate(None, text_characters)
                return len(non_text) / len(chunk) > 0.30

        except OSError:
            return True

    def evaluate_file(self, file_path: Path) -> tuple[bool, SkipReason | None, str | None, int]:
        """
        Runs all safety checks on a file.
        Returns:
            (is_safe, skip_reason, skip_detail, file_size)
        """
        # 1. Symlink traversal check
        if file_path.is_symlink() and not self.is_symlink_safe(file_path):
            return False, SkipReason.IGNORED_BY_RULE, "Symlink escapes repository root", 0

        # 2. File size check
        too_large, size = self.is_file_too_large(file_path)
        if too_large:
            detail = f"File size ({size} bytes) exceeds limit ({self.max_file_size_bytes} bytes)"
            return False, SkipReason.FILE_TOO_LARGE, detail, size

        # 3. Binary detection check
        if self.is_binary_file(file_path):
            return False, SkipReason.BINARY_FILE, "Detected binary contents (null bytes or non-text data)", size

        return True, None, None, size