import logging
from pathlib import Path
import tree_sitter

from parsing.models import ChunkType, CodeChunk
from parsing.parser import LanguageRegistry, default_registry

logger = logging.getLogger(__name__)

DEFAULT_MAX_LINES = 150
DEFAULT_MAX_CHARS = 8000


def get_node_span(node: tree_sitter.Node) -> tuple[int, int]:
    """
    Returns 1-indexed (start_line, end_line) accounting for Tree-sitter's
    (row, column=0) boundary behavior where column=0 indicates termination
    at the start of the subsequent line.
    """
    start_line = node.start_point.row + 1
    end_row = node.end_point.row
    if node.end_point.column == 0 and end_row > node.start_point.row:
        end_row -= 1
    end_line = end_row + 1
    return start_line, end_line


class ASTChunker:
    """
    Traverses Tree-sitter AST nodes and extracts semantic CodeChunk instances,
    preventing class-method duplication by generating class skeletons and correctly
    unpacking decorated definitions.
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

        # 1. Module Docstring Check
        docstring_chunk, first_stmt_idx = self._extract_module_docstring(
            root, source_lines, file_path
        )
        if docstring_chunk:
            chunks.append(docstring_chunk)

        # 2. Iterate Statements
        pending_block_nodes: list[tree_sitter.Node] = []
        children = root.children

        for i in range(first_stmt_idx, len(children)):
            child = children[i]

            if child.type == "comment":
                pending_block_nodes.append(child)
                continue

            target_node = child
            if child.type == "decorated_definition":
                target_node = self._unwrap_decorated(child)

            if target_node.type in ("function_definition", "class_definition"):
                if pending_block_nodes:
                    block_chunk = self._create_block_chunk(pending_block_nodes, source_lines, file_path)
                    if block_chunk:
                        chunks.append(block_chunk)
                    pending_block_nodes = []

                if target_node.type == "class_definition":
                    chunks.extend(
                        self._process_class_definition(
                            outer_node=child,
                            inner_class_node=target_node,
                            source_lines=source_lines,
                            file_path=file_path,
                        )
                    )
                else:
                    chunks.extend(
                        self._process_function_definition(
                            outer_node=child,
                            inner_func_node=target_node,
                            source_lines=source_lines,
                            file_path=file_path,
                        )
                    )
            else:
                pending_block_nodes.append(child)

        # Flush residual top-level statements
        if pending_block_nodes:
            block_chunk = self._create_block_chunk(pending_block_nodes, source_lines, file_path)
            if block_chunk:
                chunks.append(block_chunk)

        # 3. Apply Threshold Enforcement
        enforced_chunks: list[CodeChunk] = []
        for chunk in chunks:
            enforced_chunks.extend(self._enforce_limits(chunk))

        return enforced_chunks

    @staticmethod
    def _unwrap_decorated(node: tree_sitter.Node) -> tree_sitter.Node:
        """Finds inner class_definition or function_definition inside decorated_definition."""
        for child in node.children:
            if child.type in ("class_definition", "function_definition"):
                return child
        return node

    def _extract_module_docstring(
        self,
        root: tree_sitter.Node,
        source_lines: list[str],
        file_path: Path,
    ) -> tuple[CodeChunk | None, int]:
        children = root.children
        for idx, child in enumerate(children):
            if child.type == "comment":
                continue
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        start_line, end_line = get_node_span(child)
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
        outer_node: tree_sitter.Node,
        inner_class_node: tree_sitter.Node,
        source_lines: list[str],
        file_path: Path,
        parent_scope: str | None = None,
    ) -> list[CodeChunk]:
        results: list[CodeChunk] = []

        # Extract name directly from inner class_definition
        name_node = inner_class_node.child_by_field_name("name")
        class_name = name_node.text.decode("utf-8") if name_node and name_node.text else "AnonymousClass"
        full_class_name = f"{parent_scope}.{class_name}" if parent_scope else class_name

        body_node = inner_class_node.child_by_field_name("body")
        methods_and_subclasses: list[tuple[tree_sitter.Node, tree_sitter.Node]] = []

        skeleton_lines: list[str] = []
        outer_start_line, outer_end_line = get_node_span(outer_node)

        if body_node:
            body_start_line, _ = get_node_span(body_node)
            # Add class signature lines and decorators
            skeleton_lines.extend(source_lines[outer_start_line - 1 : body_start_line - 1])

            for member in body_node.children:
                if member.type == "comment":
                    m_start, m_end = get_node_span(member)
                    skeleton_lines.extend(source_lines[m_start - 1 : m_end])
                    continue

                target_member = member
                if member.type == "decorated_definition":
                    target_member = self._unwrap_decorated(member)

                if target_member.type in ("function_definition", "class_definition"):
                    methods_and_subclasses.append((member, target_member))
                    # Retain signature outline in skeleton
                    m_start, _ = get_node_span(member)
                    func_body = target_member.child_by_field_name("body")
                    if func_body:
                        fb_start, _ = get_node_span(func_body)
                        # Append up to the start of the body block + stub
                        sig = "".join(source_lines[m_start - 1 : fb_start - 1]).rstrip()
                        indent = " " * 8
                        skeleton_lines.append(f"{sig}\n{indent}...\n")
                    else:
                        m_end = get_node_span(member)[1]
                        skeleton_lines.extend(source_lines[m_start - 1 : m_end])
                else:
                    # Capture class attributes, docstrings, type annotations
                    m_start, m_end = get_node_span(member)
                    skeleton_lines.extend(source_lines[m_start - 1 : m_end])
        else:
            skeleton_lines.extend(source_lines[outer_start_line - 1 : outer_end_line])

        # 1. Emit Class Skeleton
        results.append(
            CodeChunk(
                file_path=file_path,
                chunk_type=ChunkType.CLASS,
                identifier=full_class_name,
                parent_scope=parent_scope,
                start_line=outer_start_line,
                end_line=outer_end_line,
                content="".join(skeleton_lines).rstrip(),
            )
        )

        # 2. Extract Methods & Subclasses
        for outer_member, inner_member in methods_and_subclasses:
            if inner_member.type == "class_definition":
                results.extend(
                    self._process_class_definition(
                        outer_node=outer_member,
                        inner_class_node=inner_member,
                        source_lines=source_lines,
                        file_path=file_path,
                        parent_scope=full_class_name,
                    )
                )
            else:
                results.extend(
                    self._process_function_definition(
                        outer_node=outer_member,
                        inner_func_node=inner_member,
                        source_lines=source_lines,
                        file_path=file_path,
                        parent_scope=full_class_name,
                        is_method=True,
                    )
                )

        return results

    def _process_function_definition(
        self,
        outer_node: tree_sitter.Node,
        inner_func_node: tree_sitter.Node,
        source_lines: list[str],
        file_path: Path,
        parent_scope: str | None = None,
        is_method: bool = False,
    ) -> list[CodeChunk]:
        name_node = inner_func_node.child_by_field_name("name")
        ident = name_node.text.decode("utf-8") if name_node and name_node.text else "anonymous"

        start_line, end_line = get_node_span(outer_node)
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
        if not nodes:
            return None

        start_line, _ = get_node_span(nodes[0])
        _, end_line = get_node_span(nodes[-1])
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
        if chunk.line_count <= self.max_lines and len(chunk.content) <= self.max_chars:
            return [chunk]

        logger.info(
            "Chunk %s [%s] exceeds limits. Applying windowing.",
            chunk.identifier or "<block>",
            chunk.chunk_type.value,
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