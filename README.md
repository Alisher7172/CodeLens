# CodeLens — Codebase Ingestion Engine

A high-performance, robust ingestion pipeline designed to traverse local repositories, apply multi-layer exclusion rules (built-in filters + standard `.gitignore`), perform pre-read safety validations, and output a structured, strongly typed in-memory snapshot of codebase text contents.

---

## Features

- **Pydantic v2 Contracts**: Strongly typed, schema-validated models for files, skipped metadata, and snapshot aggregations.
- **Dynamic Aggregations**: Automatic byte-size and document-count calculation via `@computed_field`.
- **GitIgnore-Compliant Rule Engine**: Evaluates standard `.gitignore` syntax (wildcards, directory boundaries, path negation `!`) via `pathspec`.
- **Sensible Built-in Exclusions**: Out-of-the-box filtering for VCS folders (`.git`), dependency trees (`node_modules`), environments (`.venv`), lockfiles, and media/binary extensions.
- **Pre-Read Safety Guards**:
  - **Symlink Escape Prevention**: Blocks traversal outside the repository root.
  - **Configurable Max Size**: Avoids loading oversized files into memory (default: 500 KB).
  - **Memory-Safe Binary Detection**: Sniffs the leading 1 KB buffer for null bytes and non-text byte distributions before committing to a full file read.
- **Top-Down Directory Pruning**: Early pruning of excluded directories during traversal to eliminate unnecessary disk I/O.

---

## Project Structure

```text
CodeLens/
├── pyproject.toml              # Build metadata and dependency declarations
├── README.md                   # Project documentation
├── src/
│   └── codelens/
│       ├── __init__.py         # Public API exports
│       ├── models.py           # Core Pydantic data schemas & enums
│       ├── filters.py          # Built-in exclusions & .gitignore pattern matcher
│       ├── safety.py           # Binary sniffer, size threshold, symlink resolver
│       └── crawler.py          # Top-down directory crawler & snapshot builder
└── tests/
    ├── __init__.py
    ├── test_models.py          # Validation & computed field tests
    ├── test_filters.py         # Pattern matching & exclusion tests
    ├── test_safety.py          # Size limits, binary checks, and symlink jail tests
    └── test_crawler.py         # End-to-end traversal and snapshot tests



Installation & Setup
Requirements
    Python 3.10+
    Virtual environment (recommended)