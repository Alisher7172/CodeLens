from pathlib import Path
import pytest
from pydantic import ValidationError
from parsing.models import ChunkType, CodeChunk


def test_code_chunk_inverted_lines_raises_validation_error():
    with pytest.raises(ValidationError) as exc_info:
        CodeChunk(
            file_path=Path("test.py"),
            chunk_type=ChunkType.FUNCTION,
            identifier="broken_span",
            start_line=10,
            end_line=5,
            content="def broken_span(): pass",
        )

    assert "end_line (5) cannot be less than start_line (10)" in str(exc_info.value)