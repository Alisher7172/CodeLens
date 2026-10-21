# src/codelens/filters.py
from pathlib import Path
import pathspec

DEFAULT_EXCLUSIONS: list[str] = [
    # Version control & environments
    ".git/",
    ".venv/",
    "venv/",
    "env/",
    ".env",

    # Dependencies & caches
    "node_modules/",
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",

    # OS generated files
    ".DS_Store",
    "Thumbs.db",

    # Common lockfiles
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "Pipfile.lock",

    # Common binaries, archives, and compiled outputs
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.webp",
    "*.ico",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.7z",
    "*.exe",
    "*.dll",
    "*.so",
    "*.dylib",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
]


class IgnoreRuleMatcher:
    """Evaluates relative paths against default exclusions and repository .gitignore rules."""

    def __init__(self, root_dir: Path, custom_rules: list[str] | None = None) -> None:
        self.root_dir = root_dir.resolve()

        all_rules = list(DEFAULT_EXCLUSIONS)

        gitignore_path = self.root_dir / ".gitignore"
        if gitignore_path.is_file():
            try:
                content = gitignore_path.read_text(encoding="utf-8", errors="ignore")
                all_rules.extend(content.splitlines())
            except OSError:
                pass

        if custom_rules:
            all_rules.extend(custom_rules)

        # Using modern 'gitignore' pattern syntax without deprecation warnings
        self._spec = pathspec.PathSpec.from_lines("gitignore", all_rules)

    def is_ignored(self, relative_path: Path | str, is_dir: bool = False) -> bool:
        """Check if a given relative path matches any exclusion or gitignore pattern."""
        path_str = str(relative_path).replace("\\", "/")
        if is_dir and not path_str.endswith("/"):
            path_str += "/"

        return self._spec.match_file(path_str)