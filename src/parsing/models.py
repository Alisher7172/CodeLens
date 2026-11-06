# src/codelens/parsing/models.py
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class ChunkType(str, Enum):
    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    METHOD = "METHOD"
    BLOCK = "BLOCK"
    MODULE_DOCSTRING = "MODULE_DOCSTRING"


class CodeChunk(BaseModel):
    """
    Immutable representation of an AST-derived code chunk.
    """
    model_config = ConfigDict(frozen=True)

    file_path: Path = Field(
        ...,
        description="Path relative to the root directory."
    )
    chunk_type: ChunkType = Field(
        ...,
        description="Semantic category of the chunk."
    )
    identifier: str | None = Field(
        default=None,
        description="Name of the function, method, or class if applicable."
    )
    parent_scope: str | None = Field(
        default=None,
        description="Enclosing class/scope name for methods or nested declarations."
    )
    start_line: int = Field(
        ...,
        ge=1,
        description="1-indexed line where the chunk starts."
    )
    end_line: int = Field(
        ...,
        ge=1,
        description="1-indexed line where the chunk ends."
    )
    content: str = Field(
        ...,
        description="Exact source code slice."
    )

    @model_validator(mode="after")
    def validate_line_span(self) -> "CodeChunk":
        if self.end_line < self.start_line:
            raise ValueError(
                f"end_line ({self.end_line}) cannot be less than start_line ({self.start_line})"
            )
        return self

    @computed_field
    @property
    def line_count(self) -> int:
        """Total lines spanned by this chunk (inclusive)."""
        return self.end_line - self.start_line + 1