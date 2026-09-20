#!/usr/bin/env python3
"""
review.py - AI Code Reviewer

A heuristic, rule-based static analyzer for Python source code. It is
built entirely on Python's standard library `ast` module - there is no
LLM call involved. Think of it as a small, opinionated "smart linter"
that flags common complexity problems and anti-patterns and explains
why they matter.

Usage:
    python review.py path/to/file_or_directory
    python review.py path/to/file_or_directory --severity warning error
    python review.py . --severity error

Exit status is always 0 (this is a reporting tool, not a gate), unless
an unrecoverable error occurs (e.g. the path does not exist).
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from dataclasses import dataclass
from collections import defaultdict, Counter

# ---------------------------------------------------------------------------
# Configuration / thresholds
# ---------------------------------------------------------------------------

__version__ = "0.1.0"

COMPLEXITY_WARN_THRESHOLD = 10
COMPLEXITY_ERROR_THRESHOLD = 15
LONG_FUNCTION_LINES = 50
MAX_PARAMETERS = 5
MAX_NESTING_DEPTH = 4
MIN_DUPLICATE_STATEMENTS = 3

# Single-letter names that are conventionally acceptable as loop counters
# or math-style coordinates when used directly as a `for` target.
ALLOWED_SHORT_LOOP_NAMES = {"i", "j", "k", "_"}
# Names that are never flagged no matter where they appear.
ALWAYS_ALLOWED_NAMES = {"_", "self", "cls"}

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
SEVERITY_CHOICES = ("error", "warning", "info")

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache"}


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    file: str
    line: int
    category: str
    severity: str
    message: str
    suggestion: str

    def format(self) -> str:
        return (
            f"{self.file}:{self.line}: [{self.severity.upper()}] {self.category}\n"
            f"    {self.message}\n"
            f"    Suggestion: {self.suggestion}"
        )


# ---------------------------------------------------------------------------
# Cyclomatic complexity (McCabe)
# ---------------------------------------------------------------------------

_DECISION_NODE_TYPES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.Assert, ast.IfExp)
_MATCH_CASE_TYPE = getattr(ast, "match_case", None)


def compute_complexity(func_node: ast.AST) -> int:
    """Compute the McCabe cyclomatic complexity of a function.

    Starts at 1 (single path through the function) and adds 1 for every
    additional decision point: if/elif, for, while, except clauses,
    boolean operators (and/or), ternary expressions, comprehension
    filters, assert statements, and match cases. Nested function/class
    definitions are NOT descended into - they are analyzed separately
    as their own units.
    """
    complexity = 1
    stack = list(ast.iter_child_nodes(func_node))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            # Nested scope - counted independently, don't descend.
            continue
        if isinstance(node, _DECISION_NODE_TYPES):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += max(len(node.values) - 1, 0)
        elif isinstance(node, ast.comprehension):
            complexity += len(node.ifs)
        elif _MATCH_CASE_TYPE is not None and isinstance(node, _MATCH_CASE_TYPE):
            complexity += 1
        stack.extend(ast.iter_child_nodes(node))
    return complexity


# ---------------------------------------------------------------------------
# Nesting depth
# ---------------------------------------------------------------------------

_NESTING_NODE_TYPES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)


def max_nesting_depth(func_node: ast.AST) -> int:
    """Return the deepest nesting level of control-flow blocks in a function.

    A function with no nested blocks is depth 0; a single `if` is depth 1;
    an `if` inside a `for` inside a `while` is depth 3, and so on.
    """
    best = 0

    def walk(node, depth):
        nonlocal best
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            if isinstance(child, _NESTING_NODE_TYPES):
                new_depth = depth + 1
                best = max(best, new_depth)
                walk(child, new_depth)
            else:
                walk(child, depth)

    walk(func_node, 0)
    return best


# ---------------------------------------------------------------------------
# Duplicate code detection (normalized AST hashing)
# ---------------------------------------------------------------------------

_IGNORED_IDENTIFIER_FIELDS = {"id", "arg", "name", "attr"}


def _normalize(node):
    """Turn an AST node into a structure-only fingerprint.

    Identifiers and literal values are stripped out so that two functions
    with the same *shape* (same control flow, same operations) but
    different variable names / constants hash identically.
    """
    if isinstance(node, ast.AST):
        parts = [type(node).__name__]
        for field_name, value in ast.iter_fields(node):
            if field_name in _IGNORED_IDENTIFIER_FIELDS:
                continue
            parts.append(_normalize(value))
        return tuple(parts)
    if isinstance(node, list):
        return tuple(_normalize(v) for v in node)
    if isinstance(node, (int, float, complex, str, bytes, bool)) or node is None:
        return "CONST"
    return repr(node)


def _statement_count(body):
    count = 0
    for stmt in body:
        count += 1
        for _ in ast.walk(stmt):
            count += 1
    return count


def find_duplicate_functions(tree):
    """Group functions in a module by structural (normalized) fingerprint.

    Returns a dict mapping fingerprint-hash -> list of FunctionDef/AsyncFunctionDef
    nodes that are structurally near-identical. Trivial short functions
    (e.g. a single `pass` or a one-line getter) are excluded to keep the
    signal-to-noise ratio reasonable.
    """
    groups = defaultdict(list)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant) and isinstance(s.value.value, str))]
            if not body or _statement_count(body) < MIN_DUPLICATE_STATEMENTS:
                continue
            fingerprint = hash(_normalize(body))
            groups[fingerprint].append(node)
    return {k: v for k, v in groups.items() if len(v) > 1}


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class FileAnalyzer:
    def __init__(self, filename: str, source: str, tree: ast.AST):
        self.filename = filename
        self.source = source
        self.tree = tree
        self.findings: list[Finding] = []

    def add(self, node_or_line, category, severity, message, suggestion):
        line = node_or_line.lineno if hasattr(node_or_line, "lineno") else node_or_line
        self.findings.append(Finding(self.filename, line, category, severity, message, suggestion))

    # -- individual checks --------------------------------------------------

    def check_complexity(self, node, label):
        c = compute_complexity(node)
        if c > COMPLEXITY_ERROR_THRESHOLD:
            self.add(node, "high-complexity", "error",
                      f"{label} has a cyclomatic complexity of {c} (threshold: {COMPLEXITY_ERROR_THRESHOLD}).",
                      "Break this into smaller helper functions, each handling one branch of logic.")
        elif c > COMPLEXITY_WARN_THRESHOLD:
            self.add(node, "high-complexity", "warning",
                      f"{label} has a cyclomatic complexity of {c} (threshold: {COMPLEXITY_WARN_THRESHOLD}).",
                      "Consider simplifying conditionals or extracting sub-routines to reduce branching.")

    def check_length(self, node, label):
        end_line = getattr(node, "end_lineno", None)
        if end_line is None:
            return
        length = end_line - node.lineno + 1
        if length > LONG_FUNCTION_LINES:
            self.add(node, "long-function", "warning",
                      f"{label} is {length} lines long (threshold: {LONG_FUNCTION_LINES}).",
                      "Split this function into smaller, single-purpose functions to improve readability and testability.")

    def check_parameters(self, node, label, is_method):
        args = node.args
        count = len(args.args) + len(args.posonlyargs) + len(args.kwonlyargs)
        count += 1 if args.vararg else 0
        count += 1 if args.kwarg else 0
        if is_method and (args.args or args.posonlyargs):
            count -= 1  # discount self/cls
        if count > MAX_PARAMETERS:
            self.add(node, "too-many-parameters", "warning",
                      f"{label} takes {count} parameters (threshold: {MAX_PARAMETERS}).",
                      "Group related parameters into a dataclass/dict, or split the function into smaller ones.")

    def check_nesting(self, node, label):
        depth = max_nesting_depth(node)
        if depth > MAX_NESTING_DEPTH:
            self.add(node, "deep-nesting", "warning",
                      f"{label} has a maximum nesting depth of {depth} (threshold: {MAX_NESTING_DEPTH}).",
                      "Use early returns / guard clauses, or extract inner blocks into helper functions to flatten the structure.")

    def check_mutable_defaults(self, node, label):
        defaults = list(node.args.defaults) + list(node.args.kw_defaults)
        for default in defaults:
            if default is not None and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                kind = {"List": "list", "Dict": "dict", "Set": "set"}[type(default).__name__]
                self.add(default, "mutable-default-argument", "error",
                          f"{label} uses a mutable {kind} literal as a default argument value.",
                          f"Use `None` as the default and create the {kind} inside the function body instead "
                          f"(mutable defaults are evaluated once and shared across all calls).")

    def check_docstring(self, node, label):
        if node.name.startswith("_"):
            return  # private/dunder - not part of the public API
        if ast.get_docstring(node) is None:
            self.add(node, "missing-docstring", "info",
                      f"{label} is public but has no docstring.",
                      "Add a docstring describing what it does, its parameters, and its return value.")

    def check_bare_except(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                self.add(node, "bare-except", "error",
                          "Bare `except:` clause catches every exception, including KeyboardInterrupt and SystemExit.",
                          "Catch a specific exception type (e.g. `except ValueError:`) or at least `except Exception:`.")

    def check_unused_imports(self):
        imported = {}  # name -> (line, display)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    imported[bound] = (node.lineno, alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    bound = alias.asname or alias.name
                    imported[bound] = (node.lineno, alias.asname or alias.name)

        used = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                pass  # base Name is already captured separately

        for name, (line, display) in imported.items():
            if name not in used and name != "*":
                self.add(line, "unused-import", "info",
                          f"Imported name '{display}' does not appear to be used anywhere in the file.",
                          f"Remove the unused import of '{display}', or prefix with `_` if it is intentionally re-exported.")

    def check_short_names(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.For):
                # Names bound directly by a for-loop target are conventional
                # loop counters and are allowed even if single-letter.
                continue
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self._check_name_target(target, node.lineno)
            elif isinstance(node, ast.AnnAssign) and node.target is not None:
                self._check_name_target(node.target, node.lineno)

        # Function/lambda parameters
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
                for arg in all_args:
                    if len(arg.arg) == 1 and arg.arg not in ALWAYS_ALLOWED_NAMES and arg.arg not in ALLOWED_SHORT_LOOP_NAMES:
                        self.add(arg.lineno if hasattr(arg, "lineno") else node.lineno,
                                  "non-descriptive-name", "info",
                                  f"Parameter '{arg.arg}' in function '{node.name}' is a single, non-descriptive letter.",
                                  "Use a descriptive name that conveys what the value represents.")

    def _check_name_target(self, target, lineno):
        # Skip names bound inside a `for ... in ...:` target (handled above)
        if isinstance(target, ast.Name):
            name = target.id
            if len(name) == 1 and name not in ALWAYS_ALLOWED_NAMES and name not in ALLOWED_SHORT_LOOP_NAMES:
                self.add(lineno, "non-descriptive-name", "info",
                          f"Variable '{name}' is a single, non-descriptive letter.",
                          "Use a descriptive name that conveys what the value represents (e.g. 'count', 'total', 'user').")
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._check_name_target(elt, lineno)

    def check_duplicates(self):
        groups = find_duplicate_functions(self.tree)
        for fingerprint, nodes in groups.items():
            names = ", ".join(f"'{n.name}' (line {n.lineno})" for n in nodes)
            for node in nodes:
                others = [n for n in nodes if n is not node]
                other_names = ", ".join(f"'{n.name}' (line {n.lineno})" for n in others)
                self.add(node, "duplicate-code", "warning",
                          f"Function '{node.name}' has structurally near-identical logic to: {other_names}.",
                          "Extract the shared logic into a single reusable function and have both call sites use it.")

    # -- driver ---------------------------------------------------------

    def analyze(self):
        visitor = _Visitor(self)
        visitor.visit(self.tree)
        self.check_bare_except()
        self.check_unused_imports()
        self.check_short_names()
        self.check_duplicates()
        self.findings.sort(key=lambda f: (f.line, SEVERITY_ORDER.get(f.severity, 99)))
        return self.findings


class _Visitor(ast.NodeVisitor):
    """Walks the module tracking whether we're inside a class, so that
    method parameter counts can discount `self`/`cls`."""

    def __init__(self, analyzer: FileAnalyzer):
        self.analyzer = analyzer
        self.class_depth = 0

    def visit_ClassDef(self, node):
        self.analyzer.check_docstring(node, f"Class '{node.name}'")
        self.class_depth += 1
        self.generic_visit(node)
        self.class_depth -= 1

    def _visit_function(self, node):
        is_method = self.class_depth > 0
        label = f"{'Method' if is_method else 'Function'} '{node.name}'"
        self.analyzer.check_complexity(node, label)
        self.analyzer.check_length(node, label)
        self.analyzer.check_parameters(node, label, is_method)
        self.analyzer.check_nesting(node, label)
        self.analyzer.check_mutable_defaults(node, label)
        self.analyzer.check_docstring(node, label)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_function(node)


def analyze_source(filename: str, source: str) -> list[Finding]:
    """Parse and analyze a single source string. Raises SyntaxError on
    unparsable input (caller is expected to handle it)."""
    tree = ast.parse(source, filename=filename)
    analyzer = FileAnalyzer(filename, source, tree)
    return analyzer.analyze()


def analyze_file(path: str) -> list[Finding]:
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    return analyze_source(path, source)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_python_files(path: str) -> list[str]:
    if os.path.isfile(path):
        return [path]
    results = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".py"):
                results.append(os.path.join(root, name))
    return sorted(results)


# ---------------------------------------------------------------------------
# CLI / reporting
# ---------------------------------------------------------------------------

def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="review.py",
        description="Heuristic, AST-based Python code reviewer (no LLM involved).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument("path", help="Path to a .py file or a directory to scan recursively.")
    parser.add_argument(
        "--severity",
        nargs="+",
        choices=SEVERITY_CHOICES,
        default=None,
        help="Only show findings with the given severity level(s) (default: show all).",
    )
    return parser


def print_report(all_findings: dict, severity_filter):
    total_shown = 0
    category_counts = Counter()
    severity_counts = Counter()

    for filename, findings in all_findings.items():
        if isinstance(findings, Exception):
            print(f"{filename}: could not be analyzed ({findings})")
            continue
        shown = [f for f in findings if severity_filter is None or f.severity in severity_filter]
        if not shown:
            continue
        print(f"\n=== {filename} ===")
        for finding in shown:
            print(finding.format())
            category_counts[finding.category] += 1
            severity_counts[finding.severity] += 1
            total_shown += 1

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if total_shown == 0:
        print("No findings.")
        return

    print(f"Total findings: {total_shown}")
    print("\nBy severity:")
    for sev in SEVERITY_CHOICES:
        if severity_counts.get(sev):
            print(f"  {sev:8s}: {severity_counts[sev]}")

    print("\nBy category:")
    for category, count in sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {category:28s}: {count}")


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not os.path.exists(args.path):
        print(f"error: path not found: {args.path}", file=sys.stderr)
        return 2

    files = discover_python_files(args.path)
    if not files:
        print(f"No .py files found under {args.path}")
        return 0

    severity_filter = set(args.severity) if args.severity else None

    all_findings = {}
    for path in files:
        try:
            all_findings[path] = analyze_file(path)
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            # A single unreadable/undecodable/unparsable file should not
            # abort analysis of the rest of the batch.
            all_findings[path] = exc

    print_report(all_findings, severity_filter)
    return 0


if __name__ == "__main__":
    sys.exit(main())
