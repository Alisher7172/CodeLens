# src/codelens/parsing/parser.py
import threading
import tree_sitter
import tree_sitter_python


class LanguageRegistry:
    """
    Resolves file extensions to Tree-sitter Language instances and maintains
    thread-local reusable Parser instances to avoid per-file allocation overhead.
    """

    def __init__(self) -> None:
        self._languages: dict[str, tree_sitter.Language] = {}
        # Thread-local storage to safely reuse parsers in concurrent crawls
        self._thread_local = threading.local()
        self._register_defaults()

    def _register_defaults(self) -> None:
        py_language = tree_sitter.Language(tree_sitter_python.language())
        self.register_extension(".py", py_language)

    def register_extension(self, extension: str, language: tree_sitter.Language) -> None:
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        self._languages[ext] = language

    def get_language(self, extension: str) -> tree_sitter.Language | None:
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        return self._languages.get(ext)

    def get_parser_for_file(self, extension: str) -> tree_sitter.Parser | None:
        """
        Returns a cached, reusable Parser for the given file extension.
        Reuses one Parser per language per thread.
        """
        lang = self.get_language(extension)
        if lang is None:
            return None

        # Initialize thread-local dictionary if not already present on this thread
        if not hasattr(self._thread_local, "parsers"):
            self._thread_local.parsers = {}

        # Cache key based on the language instance or its extension
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        if ext not in self._thread_local.parsers:
            self._thread_local.parsers[ext] = tree_sitter.Parser(lang)

        return self._thread_local.parsers[ext]


# Global default registry instance
default_registry = LanguageRegistry()