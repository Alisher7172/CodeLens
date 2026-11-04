# src/codelens/parsing/chunker.py
import logging
from pathlib import Path
import tree_sitter

from parsing.models import ChunkType, CodeChunk
from parsing.parser import LanguageRegistry, default_registry

logger = logging.getLogger(__name__)

DEFAULT_MAX_LINES = 150
DEFAULT_MAX_CHARS = 8000


class ASTChunker:
    """
    Traverses Tree-sitter AST nodes and extracts semantic CodeChunk instances.
    """

    def __init__(
        self,
        registry: LanguageRegistry | None = None,
        max_lines: int = DEFAULT_MAX_LINES,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self.registry = registry or default_registry
        self.max_lines = max_lines
        self.max_chars = max_chars

    def chunk_source(
        self,
        file_path: Path,
        source_code: str,
    ) -> list[CodeChunk]:
        """
        Parses source_code and returns a flat list of semantic CodeChunks.
        """
        extension = file_path.suffix
        parser = self.registry.get_parser_for_file(extension)
        if not parser:
            logger.warning("No parser registered for extension %s, emitting single BLOCK", extension)
            lines = source_code.splitlines()
            return [
                CodeChunk(
                    file_path=file_path,
                    chunk_type=ChunkType.BLOCK,
                    identifier=None,
                    parent_scope=None,
                    start_line=1,
                    end_line=max(1, len(lines)),
                    content=source_code,
                )
            ]

        source_bytes = source_code.encode("utf-8")
        tree = parser.parse(source_bytes)
        root = tree.root_node

        chunks: list[CodeChunk] = []
        source_lines = source_code.splitlines(keepends=True)

        # 1. Check for module docstring
        docstring_chunk, first_stmt_idx = self._extract_module_docstring(
            root, source_lines, file_path
        )
        if docstring_chunk:
            chunks.append(docstring_chunk)

        # 2. Iterate through top-level statements
        pending_block_nodes: list[tree_sitter.Node] = []

        children = root.children
        for i in range(first_stmt_idx, len(children)):
            child = children[i]

            if child.type in ("comment",):
                pending_block_nodes.append(child)
                continue

            if child.type in ("function_definition", "decorated_definition", "class_definition"):
                # Flush pending module-level statements before processing definition
                if pending_block_nodes:
                    block_chunk = self._create_block_chunk(pending_block_nodes, source_lines, file_path)
                    if block_chunk:
                        chunks.append(block_chunk)
                    pending_block_nodes = []

                if child.type == "class_definition":
                    chunks.extend(self._process_class_definition(child, source_lines, file_path))
                else:
                    chunks.extend(self._process_function_definition(child, source_lines, file_path))
            else:
                pending_block_nodes.append(child)

        # Flush any remaining statements (plain scripts, imports, globals, etc.)
        if pending_block_nodes:
            block_chunk = self._create_block_chunk(pending_block_nodes, source_lines, file_path)
            if block_chunk:
                chunks.append(block_chunk)

        # 3. Apply windowing / size threshold split if exceeded
        enforced_chunks: list[CodeChunk] = []
        for chunk in chunks:
            enforced_chunks.extend(self._enforce_limits(chunk))

        return enforced_chunks

    def _extract_module_docstring(
        self,
        root: tree_sitter.Node,
        source_lines: list[str],
        file_path: Path,
    ) -> tuple[CodeChunk | None, int]:
        """
        Extracts top-level module docstrings if present as the first statement.
        """
        children = root.children
        for idx, child in enumerate(children):
            if child.type == "comment":
                continue
            if child.type == "expression_statement":
                # Look for string child inside expression_statement
                for sub in child.children:
                    if sub.type == "string":
                        start_line = child.start_point.row + 1
                        end_line = child.end_point.row + 1
                        content = "".join(source_lines[start_line - 1 : end_line]).strip()
                        return (
                            CodeChunk(
                                file_path=file_path,
                                chunk_type=ChunkType.MODULE_DOCSTRING,
                                identifier=None,
                                parent_scope=None,
                                start_line=start_line,
                                end_line=end_line,
                                content=content,
                            ),
                            idx + 1,
                        )
            break
        return None, 0

    def _process_class_definition(
        self,
        node: tree_sitter.Node,
        source_lines: list[str],
        file_path: Path,
        parent_scope: str | None = None,
    ) -> list[CodeChunk]:
        """
        Emits a CLASS chunk for the class declaration and individual METHOD chunks.
        """
        results: list[CodeChunk] = []
        class_name_node = node.child_by_field_name("name")
        class_name = class_name_node.text.decode("utf-8") if class_name_node and class_name_node.text else "AnonymousClass"
        full_class_name = f"{parent_scope}.{class_name}" if parent_scope else class_name

        body_node = node.child_by_field_name("body")
        methods_and_subclasses: list[tree_sitter.Node] = []

        if body_node:
            for child in body_node.children:
                if child.type in ("function_definition", "decorated_definition", "class_definition"):
                    methods_and_subclasses.append(child)

        # 1. Create chunk for class itself
        class_start_line = node.start_point.row + 1
        class_end_line = node.end_point.row + 1
        class_content = "".join(source_lines[class_start_line - 1 : class_end_line]).rstrip()

        results.append(
            CodeChunk(
                file_path=file_path,
                chunk_type=ChunkType.CLASS,
                identifier=full_class_name,
                parent_scope=parent_scope,
                start_line=class_start_line,
                end_line=class_end_line,
                content=class_content,
            )
        )

        # 2. Extract methods and nested classes
        for member in methods_and_subclasses:
            if member.type == "class_definition":
                results.extend(
                    self._process_class_definition(
                        member, source_lines, file_path, parent_scope=full_class_name
                    )
                )
            else:
                results.extend(
                    self._process_function_definition(
                        member,
                        source_lines,
                        file_path,
                        parent_scope=full_class_name,
                        is_method=True,
                    )
                )

        return results

    def _process_function_definition(
        self,
        node: tree_sitter.Node,
        source_lines: list[str],
        file_path: Path,
        parent_scope: str | None = None,
        is_method: bool = False,
    ) -> list[CodeChunk]:
        """
        Processes regular and decorated function definitions.
        Decorators remain part of the function chunk.
        """
        func_node = node
        if node.type == "decorated_definition":
            # Find the inner function_definition or class_definition
            for child in node.children:
                if child.type == "function_definition":
                    func_node = child
                    break
                if child.type == "class_definition":
                    return self._process_class_definition(
                        node, source_lines, file_path, parent_scope=parent_scope
                    )

        name_node = func_node.child_by_field_name("name")
        ident = name_node.text.decode("utf-8") if name_node and name_node.text else "anonymous"

        # The chunk encompasses the entire definition node (including decorators)
        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        content = "".join(source_lines[start_line - 1 : end_line]).rstrip()

        return [
            CodeChunk(
                file_path=file_path,
                chunk_type=ChunkType.METHOD if is_method else ChunkType.FUNCTION,
                identifier=ident,
                parent_scope=parent_scope,
                start_line=start_line,
                end_line=end_line,
                content=content,
            )
        ]

    def _create_block_chunk(
        self,
        nodes: list[tree_sitter.Node],
        source_lines: list[str],
        file_path: Path,
    ) -> CodeChunk | None:
        """
        Creates a single BLOCK chunk grouping consecutive statements.
        """
        if not nodes:
            return None

        start_line = nodes[0].start_point.row + 1
        end_line = nodes[-1].end_point.row + 1
        content = "".join(source_lines[start_line - 1 : end_line]).strip()

        if not content:
            return None

        return CodeChunk(
            file_path=file_path,
            chunk_type=ChunkType.BLOCK,
            identifier=None,
            parent_scope=None,
            start_line=start_line,
            end_line=end_line,
            content=content,
        )

    def _enforce_limits(self, chunk: CodeChunk) -> list[CodeChunk]:
        """
        Enforces max_lines or max_chars threshold.
        If chunk exceeds threshold, splits it into contiguous sub-window BLOCK chunks.
        """
        if chunk.line_count <= self.max_lines and len(chunk.content) <= self.max_chars:
            return [chunk]

        logger.info(
            "Chunk %s [%s] exceeds limits (lines=%d/%d, chars=%d/%d). Applying line windowing.",
            chunk.identifier or "<block>",
            chunk.chunk_type.value,
            chunk.line_count,
            self.max_lines,
            len(chunk.content),
            self.max_chars,
        )

        lines = chunk.content.splitlines(keepends=True)
        split_chunks: list[CodeChunk] = []

        window_start_idx = 0
        total_lines = len(lines)

        while window_start_idx < total_lines:
            window_end_idx = min(window_start_idx + self.max_lines, total_lines)
            sub_lines = lines[window_start_idx:window_end_idx]
            sub_content = "".join(sub_lines).rstrip()

            sub_start_line = chunk.start_line + window_start_idx
            sub_end_line = sub_start_line + len(sub_lines) - 1

            split_chunks.append(
                CodeChunk(
                    file_path=chunk.file_path,
                    chunk_type=chunk.chunk_type,
                    identifier=f"{chunk.identifier}#L{sub_start_line}-L{sub_end_line}"
                    if chunk.identifier
                    else None,
                    parent_scope=chunk.parent_scope,
                    start_line=sub_start_line,
                    end_line=sub_end_line,
                    content=sub_content,
                )
            )
            window_start_idx = window_end_idx

        return split_chunks