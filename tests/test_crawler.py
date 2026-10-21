# tests/test_crawler.py
from pathlib import Path
import pytest
from ingestion.crawler import crawl_repository
from ingestion.models import SkipReason


def test_crawl_repository_end_to_end(tmp_path: Path):
    # Set up directory structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    node_dir = tmp_path / "node_modules" / "pkg"
    node_dir.mkdir(parents=True)

    # 1. Valid source text file
    main_py = src_dir / "main.py"
    main_py.write_text("print('hello')", encoding="utf-8")

    # 2. Ignored directory file
    ignored_dep = node_dir / "index.js"
    ignored_dep.write_text("console.log('dep')", encoding="utf-8")

    # 3. Binary file
    bin_file = tmp_path / "sample.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03\x04")

    # 4. Large file
    large_file = tmp_path / "large.txt"
    large_file.write_text("A" * 1500, encoding="utf-8")

    # Crawl with a small file size limit (1000 bytes)
    snapshot = crawl_repository(repo_path=tmp_path, max_file_size_bytes=1000)

    # Validate ingested documents
    assert snapshot.total_files == 1
    assert snapshot.documents[0].relative_path == Path("src/main.py")
    assert snapshot.documents[0].extension == ".py"
    assert snapshot.documents[0].content == "print('hello')"

    # Validate skipped file reasons
    skipped_reasons = {s.relative_path: s.reason for s in snapshot.skipped_files}

    assert skipped_reasons[Path("node_modules")] == SkipReason.IGNORED_BY_RULE
    assert skipped_reasons[Path("sample.bin")] == SkipReason.BINARY_FILE
    assert skipped_reasons[Path("large.txt")] == SkipReason.FILE_TOO_LARGE


def test_crawl_invalid_directory():
    with pytest.raises(NotADirectoryError):
        crawl_repository("non_existent_folder_path_xyz")