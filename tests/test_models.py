# tests/test_models.py
from pathlib import Path
import pytest
from pydantic import ValidationError
from ingestion.models import FileDocument, RepositorySnapshot, SkippedFile, SkipReason


def test_file_document_negative_size():
    with pytest.raises(ValidationError):
        FileDocument(
            relative_path=Path("foo.txt"),
            extension=".txt",
            size_bytes=-1,
            content="abc",
        )


def test_repository_snapshot_computed_fields():
    doc1 = FileDocument(
        relative_path=Path("a.py"),
        extension=".py",
        size_bytes=100,
        content="x = 1",
    )
    doc2 = FileDocument(
        relative_path=Path("b.py"),
        extension=".py",
        size_bytes=250,
        content="y = 2",
    )
    skipped = SkippedFile(
        relative_path=Path(".git/HEAD"),
        reason=SkipReason.IGNORED_BY_RULE,
    )

    snapshot = RepositorySnapshot(
        root_path=Path("/tmp/repo"),
        documents=[doc1, doc2],
        skipped_files=[skipped],
    )

    assert snapshot.total_files == 2
    assert snapshot.total_bytes == 350