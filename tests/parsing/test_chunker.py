from pathlib import Path
from parsing.chunker import ASTChunker
from parsing.models import ChunkType


def test_decorated_class_and_methods():
    code = (
        "@dataclass\n"
        "class UserAccount:\n"
        "    id: int\n"
        "    name: str\n"
        "\n"
        "    def verify_credentials(self, secret: str) -> bool:\n"
        "        # Validate credentials here\n"
        "        return secret == 'ok'\n"
    )
    chunker = ASTChunker()
    chunks = chunker.chunk_source(Path("user.py"), code)

    # 1. Class must be properly identified and not "AnonymousClass"
    class_chunk = next(c for c in chunks if c.chunk_type == ChunkType.CLASS)
    assert class_chunk.identifier == "UserAccount"
    assert "@dataclass" in class_chunk.content
    assert "class UserAccount:" in class_chunk.content

    # 2. Skeleton verification: implementation should be stubbed out
    assert "return secret == 'ok'" not in class_chunk.content
    assert "..." in class_chunk.content

    # 3. Method extraction with scope populated
    method_chunk = next(c for c in chunks if c.chunk_type == ChunkType.METHOD)
    assert method_chunk.identifier == "verify_credentials"
    assert method_chunk.parent_scope == "UserAccount"
    assert "return secret == 'ok'" in method_chunk.content


def test_column_zero_slice_boundary():
    code = (
        "def first():\n"
        "    return 1\n"
        "\n"
        "def second():\n"
        "    return 2\n"
    )
    chunker = ASTChunker()
    chunks = chunker.chunk_source(Path("span.py"), code)

    first_fn = next(c for c in chunks if c.identifier == "first")
    # Tree-sitter ends line 2 before the blank line 3
    assert first_fn.start_line == 1
    assert first_fn.end_line == 2
    assert first_fn.line_count == 2