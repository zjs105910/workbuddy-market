import ast
import io
import tokenize
from collections import Counter


def _comment_tokens(source: str) -> list[tokenize.TokenInfo]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return [token for token in tokens if token.type == tokenize.COMMENT]


def _docstring_nodes(tree: ast.AST) -> list[ast.Expr]:
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    nodes = []
    for node in ast.walk(tree):
        if not isinstance(node, owners) or not node.body:
            continue
        first = node.body[0]
        is_text = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
        if is_text and isinstance(first.value.value, str):
            nodes.append(first)
    return nodes


def comment_texts(source: str) -> Counter:
    texts = Counter(token.string.strip() for token in _comment_tokens(source))
    for node in _docstring_nodes(ast.parse(source)):
        texts["doc:" + str(node.value.value).strip()] += 1
    return texts


def count_new_comments(*, before: str, after: str) -> int:
    added = comment_texts(after) - comment_texts(before)
    return sum(added.values())


def strip_comments(source: str) -> str:
    lines = source.splitlines()
    for token in reversed(_comment_tokens(source)):
        row = token.start[0] - 1
        lines[row] = lines[row][: token.start[1]].rstrip()
    docstring_lines = set()
    for node in _docstring_nodes(ast.parse(source)):
        docstring_lines.update(range(node.lineno - 1, node.end_lineno))
    kept = [line for index, line in enumerate(lines) if index not in docstring_lines]
    return "\n".join(_collapse_blank_lines(kept)).strip("\n") + "\n"


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    collapsed = []
    for line in lines:
        if line.strip() or (collapsed and collapsed[-1].strip()):
            collapsed.append(line)
    return collapsed
