# tests/test_chunker.py
from pathlib import Path
import pytest
from parsing.chunker import ASTChunker
from parsing.models import ChunkType


@pytest.fixture
def chunker() -> ASTChunker:
    return ASTChunker(max_lines=100, max_chars=5000)


def test_standalone_functions_and_decorators(chunker: ASTChunker):
    code = (
        "@decorator_one\n"
        "@decorator_two(param='val')\n"
        "def compute_hash(data: str) -> str:\n"
        "    \"\"\"Docstring.\"\"\"\n"
        "    return data.strip()\n"
    )
    chunks = chunker.chunk_source(Path("crypto.py"), code)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_type == ChunkType.FUNCTION
    assert chunk.identifier == "compute_hash"
    assert chunk.parent_scope is None
    assert chunk.start_line == 1
    assert chunk.end_line == 5
    assert chunk.line_count == 5
    # Decorators must remain attached
    assert "@decorator_one" in chunk.content
    assert "@decorator_two" in chunk.content
    assert "return data.strip()" in chunk.content


def test_class_with_multiple_methods_and_nested_scope(chunker: ASTChunker):
    code = (
        "class FileSafetyChecker:\n"
        "    def __init__(self, root: str):\n"
        "        self.root = root\n"
        "\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        return cls('.')\n"
        "\n"
        "    class InnerConfig:\n"
        "        def validate(self):\n"
        "            pass\n"
    )
    chunks = chunker.chunk_source(Path("safety.py"), code)

    types = [c.chunk_type for c in chunks]
    assert ChunkType.CLASS in types
    assert ChunkType.METHOD in types

    # 1. Main class
    outer_class = next(c for c in chunks if c.chunk_type == ChunkType.CLASS and c.identifier == "FileSafetyChecker")
    assert outer_class.parent_scope is None

    # 2. Methods inside FileSafetyChecker
    init_method = next(c for c in chunks if c.identifier == "__init__")
    assert init_method.chunk_type == ChunkType.METHOD
    assert init_method.parent_scope == "FileSafetyChecker"
    assert init_method.start_line == 2
    assert init_method.end_line == 3

    create_method = next(c for c in chunks if c.identifier == "create")
    assert create_method.chunk_type == ChunkType.METHOD
    assert create_method.parent_scope == "FileSafetyChecker"
    assert create_method.start_line == 5
    assert "@classmethod" in create_method.content

    # 3. Nested class and method
    inner_class = next(c for c in chunks if c.identifier == "FileSafetyChecker.InnerConfig")
    assert inner_class.chunk_type == ChunkType.CLASS
    assert inner_class.parent_scope == "FileSafetyChecker"

    validate_method = next(c for c in chunks if c.identifier == "validate")
    assert validate_method.chunk_type == ChunkType.METHOD
    assert validate_method.parent_scope == "FileSafetyChecker.InnerConfig"


def test_standalone_script_procedural_statements(chunker: ASTChunker):
    code = (
        "import os\n"
        "import sys\n"
        "\n"
        "x = 10\n"
        "y = 20\n"
        "print(x + y)\n"
    )
    chunks = chunker.chunk_source(Path("run.py"), code)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_type == ChunkType.BLOCK
    assert chunk.identifier is None
    assert chunk.parent_scope is None
    assert chunk.start_line == 1
    assert chunk.end_line == 6
    assert chunk.line_count == 6
    assert "import os" in chunk.content
    assert "print(x + y)" in chunk.content


def test_module_docstring_and_blocks(chunker: ASTChunker):
    code = (
        "\"\"\"Module header documentation.\"\"\"\n"
        "\n"
        "import sys\n"
        "\n"
        "def main():\n"
        "    pass\n"
    )
    chunks = chunker.chunk_source(Path("main.py"), code)

    assert len(chunks) == 3
    assert chunks[0].chunk_type == ChunkType.MODULE_DOCSTRING
    assert chunks[0].content == "\"\"\"Module header documentation.\"\"\""

    assert chunks[1].chunk_type == ChunkType.BLOCK
    assert "import sys" in chunks[1].content

    assert chunks[2].chunk_type == ChunkType.FUNCTION
    assert chunks[2].identifier == "main"


def test_line_number_accuracy(chunker: ASTChunker):
    lines = [
        "# Comment line 1",                 # 1
        "a = 1",                            # 2
        "",                                 # 3
        "def first_fn():",                  # 4
        "    return 42",                    # 5
        "",                                 # 6
        "def second_fn():",                 # 7
        "    line_one = 1",                 # 8
        "    line_two = 2",                 # 9
        "    return line_one + line_two",   # 10
    ]
    code = "\n".join(lines)
    chunks = chunker.chunk_source(Path("lines.py"), code)

    first_fn = next(c for c in chunks if c.identifier == "first_fn")
    assert first_fn.start_line == 4
    assert first_fn.end_line == 5
    assert first_fn.line_count == 2

    second_fn = next(c for c in chunks if c.identifier == "second_fn")
    assert second_fn.start_line == 7
    assert second_fn.end_line == 10
    assert second_fn.line_count == 4


def test_max_lines_windowing_threshold():
    # Instantiate chunker with small max_lines threshold = 5
    small_chunker = ASTChunker(max_lines=5)
    code = (
        "def long_computation():\n"
        "    a = 1\n"
        "    b = 2\n"
        "    c = 3\n"
        "    d = 4\n"
        "    e = 5\n"
        "    f = 6\n"
        "    return a + b + c + d + e + f\n"
    )
    chunks = small_chunker.chunk_source(Path("long.py"), code)

    # Function has 8 lines, should be split into 2 sub-window chunks (5 lines + 3 lines)
    assert len(chunks) == 2
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 5
    assert chunks[0].line_count == 5

    assert chunks[1].start_line == 6
    assert chunks[1].end_line == 8
    assert chunks[1].line_count == 3