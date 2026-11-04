# src/codelens/parsing/parser.py
from typing import Callable
import tree_sitter
import tree_sitter_python


class LanguageRegistry:
    """
    Resolves file extensions to corresponding Tree-sitter Language instances and Parsers.
    Extensible for .ts, .js, .go, etc.
    """

    def __init__(self) -> None:
        self._languages: dict[str, tree_sitter.Language] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        # Register Python parser using modern tree-sitter language bindings
        py_language = tree_sitter.Language(tree_sitter_python.language())
        self.register_extension(".py", py_language)

    def register_extension(self, extension: str, language: tree_sitter.Language) -> None:
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        self._languages[ext] = language

    def get_language(self, extension: str) -> tree_sitter.Language | None:
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        return self._languages.get(ext)

    def get_parser_for_file(self, extension: str) -> tree_sitter.Parser | None:
        lang = self.get_language(extension)
        if lang is None:
            return None
        return tree_sitter.Parser(lang)


# Global default registry instance
default_registry = LanguageRegistry()