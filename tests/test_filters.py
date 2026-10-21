# tests/test_filters.py
from pathlib import Path
from ingestion.filters import IgnoreRuleMatcher


def test_default_exclusions(tmp_path: Path):
    matcher = IgnoreRuleMatcher(root_dir=tmp_path)

    # Excluded folders and files
    assert matcher.is_ignored(Path(".git"), is_dir=True)
    assert matcher.is_ignored(Path("node_modules"), is_dir=True)
    assert matcher.is_ignored(Path("src/__pycache__"), is_dir=True)
    assert matcher.is_ignored(Path("assets/logo.png"))
    assert matcher.is_ignored(Path("package-lock.json"))
    assert matcher.is_ignored(Path(".DS_Store"))

    # Valid code files should NOT be ignored
    assert not matcher.is_ignored(Path("src/main.py"))
    assert not matcher.is_ignored(Path("README.md"))


def test_gitignore_rules(tmp_path: Path):
    # Create a dummy .gitignore file
    gitignore_file = tmp_path / ".gitignore"
    gitignore_file.write_text("build/\n*.secret\n!important.secret\n", encoding="utf-8")

    matcher = IgnoreRuleMatcher(root_dir=tmp_path)

    # Custom rules from .gitignore
    assert matcher.is_ignored(Path("build"), is_dir=True)
    assert matcher.is_ignored(Path("config/database.secret"))

    # Negation rule ('!') should allow the file
    assert not matcher.is_ignored(Path("config/important.secret"))