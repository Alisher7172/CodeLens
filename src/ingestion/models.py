# src/ingestion/models.py
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field, computed_field


class SkipReason(str, Enum):
    IGNORED_BY_RULE = "ignored_by_rule"
    BINARY_FILE = "binary_file"
    FILE_TOO_LARGE = "file_too_large"
    ENCODING_ERROR = "encoding_error"
    PERMISSION_DENIED = "permission_denied"
    SYMLINK_ESCAPE = "symlink_escape"


class SkippedFile(BaseModel):
    model_config = {"frozen": True}
    relative_path: Path = Field(
        ...,
        description="Path relative to the root directory."
    )
    reason: SkipReason = Field(
        ...,
        description="Category explaining why the file was skipped."
    )
    detail: str | None = Field(
        default=None,
        description="Optional diagnostic context (e.g., matched rule or file size)."
    )


class FileDocument(BaseModel):
    model_config = {"frozen": True}
    relative_path: Path = Field(
        ...,
        description="File path relative to the repository root."
    )
    extension: str = Field(
        ...,
        description="File extension including the leading dot (e.g., '.py')."
    )
    size_bytes: int = Field(
        ...,
        ge=0,
        description="Exact size of the file in bytes."
    )
    content: str = Field(
        ...,
        description="Decoded UTF-8 text content."
    )


class RepositorySnapshot(BaseModel):
    root_path: Path = Field(
        ...,
        description="Absolute path to the ingested root directory."
    )
    documents: list[FileDocument] = Field(
        default_factory=list,
        description="All successfully read text files."
    )
    skipped_files: list[SkippedFile] = Field(
        default_factory=list,
        description="All skipped/excluded files."
    )

    @computed_field
    @property
    def total_files(self) -> int:
        """Count of readable text files ingested."""
        return len(self.documents)

    @computed_field
    @property
    def total_bytes(self) -> int:
        """Combined byte size of all ingested files."""
        return sum(doc.size_bytes for doc in self.documents)