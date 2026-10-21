# src/ingestion/crawler.py
import os
from pathlib import Path

from ingestion.filters import IgnoreRuleMatcher
from ingestion.models import (
    FileDocument,
    RepositorySnapshot,
    SkipReason,
    SkippedFile,
)
from ingestion.safety import DEFAULT_MAX_FILE_SIZE_BYTES, FileSafetyChecker


def crawl_repository(
    repo_path: Path | str,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    custom_ignore_rules: list[str] | None = None,
) -> RepositorySnapshot:
    """
    Traverses a repository directory, filters files using .gitignore rules and
    built-in exclusions, applies safety checks, and returns a RepositorySnapshot.
    """
    root_path = Path(repo_path).resolve()
    if not root_path.is_dir():
        raise NotADirectoryError(f"Provided path is not a valid directory: {root_path}")

    matcher = IgnoreRuleMatcher(root_dir=root_path, custom_rules=custom_ignore_rules)
    safety_checker = FileSafetyChecker(
        root_dir=root_path,
        max_file_size_bytes=max_file_size_bytes,
    )

    documents: list[FileDocument] = []
    skipped_files: list[SkippedFile] = []

    for dirpath_str, dirs, files in os.walk(root_path, topdown=True, followlinks=False):
        current_dir = Path(dirpath_str)

        # 1. Directory pruning: Filter subdirectories to avoid walking into excluded folders
        dirs_to_keep: list[str] = []
        for d in dirs:
            dir_path = current_dir / d
            rel_dir_path = dir_path.relative_to(root_path)

            if matcher.is_ignored(rel_dir_path, is_dir=True):
                skipped_files.append(
                    SkippedFile(
                        relative_path=rel_dir_path,
                        reason=SkipReason.IGNORED_BY_RULE,
                        detail="Excluded directory pattern matched",
                    )
                )
            else:
                dirs_to_keep.append(d)

        # Modifying dirs in-place directs os.walk's traversal
        dirs[:] = dirs_to_keep

        # 2. File processing
        for filename in files:
            file_path = current_dir / filename
            try:
                rel_path = file_path.relative_to(root_path)
            except ValueError:
                rel_path = Path(filename)

            # Check .gitignore & default exclusion patterns
            if matcher.is_ignored(rel_path):
                skipped_files.append(
                    SkippedFile(
                        relative_path=rel_path,
                        reason=SkipReason.IGNORED_BY_RULE,
                        detail="Matched gitignore or default exclusion rule",
                    )
                )
                continue

            # Run safety checks: symlink escape, max size, binary check
            is_safe, skip_reason, skip_detail, size_bytes = safety_checker.evaluate_file(file_path)
            if not is_safe and skip_reason is not None:
                skipped_files.append(
                    SkippedFile(
                        relative_path=rel_path,
                        reason=skip_reason,
                        detail=skip_detail,
                    )
                )
                continue

            # Read text contents
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    # Fallback to UTF-8 with replacement for slight encoding anomalies
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    skipped_files.append(
                        SkippedFile(
                            relative_path=rel_path,
                            reason=SkipReason.ENCODING_ERROR,
                            detail=str(e),
                        )
                    )
                    continue
            except PermissionError as e:
                skipped_files.append(
                    SkippedFile(
                        relative_path=rel_path,
                        reason=SkipReason.PERMISSION_DENIED,
                        detail=str(e),
                    )
                )
                continue
            except OSError as e:
                skipped_files.append(
                    SkippedFile(
                        relative_path=rel_path,
                        reason=SkipReason.IGNORED_BY_RULE,
                        detail=f"OS error reading file: {e}",
                    )
                )
                continue

            # File read successfully
            documents.append(
                FileDocument(
                    relative_path=rel_path,
                    extension=file_path.suffix,
                    size_bytes=size_bytes,
                    content=content,
                )
            )

    return RepositorySnapshot(
        root_path=root_path,
        documents=documents,
        skipped_files=skipped_files,
    )