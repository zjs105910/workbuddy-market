import ast
import json
import statistics
import subprocess
from pathlib import Path

from radon.complexity import cc_visit

from graders.comments import strip_comments

RUFF = str(Path(__file__).resolve().parent.parent / ".venv" / "bin" / "ruff")
NESTING_NODES = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncFor, ast.AsyncWith)


def _nesting_depth(node: ast.AST, depth: int = 0) -> int:
    deepest = depth
    for child in ast.iter_child_nodes(node):
        child_depth = depth + 1 if isinstance(child, NESTING_NODES) else depth
        deepest = max(deepest, _nesting_depth(child, child_depth))
    return deepest


def _identifiers(tree: ast.AST) -> list[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.append(node.id)
    return [name for name in names if name not in {"self", "cls"}]


def _ruff_warning_count(paths: list[Path]) -> int:
    if not paths:
        return 0
    completed = subprocess.run(
        [RUFF, "check", "--output-format", "json", "--no-cache", *map(str, paths)],
        capture_output=True,
        text=True,
    )
    return len(json.loads(completed.stdout or "[]"))


def measure_files(paths: list[Path]) -> dict:
    sources = [strip_comments(path.read_text()) for path in paths]
    trees = [ast.parse(source) for source in sources]
    functions = [
        node
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    lengths = [node.end_lineno - node.lineno + 1 for node in functions]
    complexities = [block.complexity for source in sources for block in cc_visit(source)]
    names = [name for tree in trees for name in _identifiers(tree)]
    return {
        "file_count": len(paths),
        "code_lines": sum(1 for source in sources for line in source.splitlines() if line.strip()),
        "function_count": len(functions),
        "mean_function_length": statistics.fmean(lengths) if lengths else 0,
        "max_function_length": max(lengths, default=0),
        "max_complexity": max(complexities, default=0),
        "mean_identifier_length": statistics.fmean(map(len, names)) if names else 0,
        "max_nesting_depth": max((_nesting_depth(tree) for tree in trees), default=0),
        "ruff_warnings": _ruff_warning_count(paths),
    }
