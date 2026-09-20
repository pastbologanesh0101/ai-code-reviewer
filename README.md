# AI Code Reviewer

A small, self-contained, **rule-based** Python code reviewer. It parses a
`.py` file's Abstract Syntax Tree (`ast` module) and flags common
complexity problems and anti-patterns — no LLM call, no network access,
no third-party dependencies. Pure Python standard library.

Think of it as a deterministic "smart linter": every finding is produced
by an explicit, inspectable rule, so the same input always produces the
same output.

## Checks performed

| Category | What it catches | Why it matters |
|---|---|---|
| `high-complexity` | McCabe cyclomatic complexity above a threshold (10 warning / 15 error), computed from real decision points: `if`/`elif`, loops, `except` clauses, `and`/`or`, ternaries, comprehension filters, `assert`, `match` cases | High branching complexity is strongly correlated with bug density and makes a function hard to reason about or test exhaustively |
| `long-function` | Functions longer than 50 lines | Long functions usually do more than one job; they're harder to read, test, and safely modify |
| `too-many-parameters` | Functions/methods with more than 5 parameters (`self`/`cls` excluded) | Long parameter lists are a sign a function needs a config object, or needs splitting; they're also easy to call with args in the wrong order |
| `deep-nesting` | Control-flow nesting deeper than 4 levels (`if`/`for`/`while`/`with`/`try`) | Deeply nested code is hard to scan visually and often hides missed edge cases; usually fixable with guard clauses |
| `mutable-default-argument` | `def f(x=[])` / `def f(x={})` / `def f(x=set())` | Classic Python footgun — the default object is created once at function-definition time and shared across every call that doesn't pass its own value |
| `bare-except` | A bare `except:` clause | Silently swallows *everything*, including `KeyboardInterrupt` and `SystemExit`, and hides real bugs |
| `unused-import` | Imported names never referenced anywhere in the file | Dead weight that slows down readers and can mask a typo'd import |
| `non-descriptive-name` | Single-letter variable/parameter names, excluding conventional loop counters (`i`, `j`, `k`) bound directly by a `for` target, and `_`/`self`/`cls` | Names like `q`, `z`, `a` carry no meaning and make code reviews and debugging slower |
| `missing-docstring` | Public functions, methods, and classes (name doesn't start with `_`) with no docstring | Undocumented public APIs are harder to use correctly and to maintain |
| `duplicate-code` | Functions whose normalized AST (identifiers/literals stripped, structure kept) hashes identically to another function's | Near-identical logic copy-pasted into two places means bug fixes have to be applied twice — and often aren't |

Each finding includes a **file, line number, severity** (`error` /
`warning` / `info`), a **human-readable explanation**, and a concrete
**suggestion** for how to fix it.

## Installation

No installation needed — it's a single-file script using only the
standard library. Requires Python 3.9+.

```bash
git clone https://github.com/pastbologanesh0101/ai-code-reviewer.git
cd ai-code-reviewer
```

## Usage

```bash
# Review a single file
python3 review.py path/to/file.py

# Recursively review every .py file in a directory
python3 review.py path/to/project/

# Only show errors and warnings (hide info-level findings)
python3 review.py path/to/project/ --severity error warning

# Only show errors
python3 review.py path/to/project/ --severity error
```

The tool always exits 0 (it's a reporting tool, not a CI gate) except when
the given path does not exist.

## Example output

The repo ships a deliberately messy sample at `samples/messy_sample.py`
that intentionally triggers every check. Running:

```bash
python3 review.py samples/messy_sample.py
```

produces output like:

```
=== samples/messy_sample.py ===
samples/messy_sample.py:7: [INFO] unused-import
    Imported name 'os' does not appear to be used anywhere in the file.
    Suggestion: Remove the unused import of 'os', or prefix with `_` if it is intentionally re-exported.
samples/messy_sample.py:13: [WARNING] duplicate-code
    Function 'add' has structurally near-identical logic to: 'add2' (line 17).
    Suggestion: Extract the shared logic into a single reusable function and have both call sites use it.
samples/messy_sample.py:21: [ERROR] mutable-default-argument
    Function 'process' uses a mutable list literal as a default argument value.
    Suggestion: Use `None` as the default and create the list inside the function body instead (mutable defaults are evaluated once and shared across all calls).
samples/messy_sample.py:21: [WARNING] deep-nesting
    Function 'process' has a maximum nesting depth of 7 (threshold: 4).
    Suggestion: Use early returns / guard clauses, or extract inner blocks into helper functions to flatten the structure.
samples/messy_sample.py:34: [WARNING] high-complexity
    Function 'compute_score' has a cyclomatic complexity of 13 (threshold: 10).
    Suggestion: Consider simplifying conditionals or extracting sub-routines to reduce branching.
samples/messy_sample.py:57: [ERROR] bare-except
    Bare `except:` clause catches every exception, including KeyboardInterrupt and SystemExit.
    Suggestion: Catch a specific exception type (e.g. `except ValueError:`) or at least `except Exception:`.
...

============================================================
SUMMARY
============================================================
Total findings: 38

By severity:
  error   : 4
  warning : 7
  info    : 27

By category:
  non-descriptive-name        : 16
  missing-docstring           : 8
  unused-import               : 3
  bare-except                 : 2
  duplicate-code              : 2
  mutable-default-argument    : 2
  too-many-parameters         : 2
  deep-nesting                : 1
  high-complexity             : 1
  long-function                : 1
```

## Running the tests

```bash
python3 -m unittest discover -s tests -v
```

The test suite (`tests/test_review.py`) includes a true-positive and
true-negative case for every major check, plus an end-to-end test that
runs the full analyzer against `samples/messy_sample.py` and asserts that
all ten finding categories are present.

## How it works (briefly)

`review.py` parses each file with `ast.parse`, then walks the tree with a
custom `ast.NodeVisitor`. Cyclomatic complexity and nesting depth are
computed by walking a function's body while deliberately *not* descending
into nested function/class definitions (they're analyzed as their own,
separate units). Duplicate-code detection normalizes each function's AST
by stripping out identifier names and literal values while keeping node
types and structure, then hashes the result — two functions with the same
control flow and operations but different variable names/constants will
collide.

## Troubleshooting / FAQ

**A file failed with "could not be analyzed" — why?**
This means the file couldn't be parsed as Python (a real `SyntaxError`,
e.g. Python 2-only syntax or a truncated file) or couldn't be decoded as
UTF-8 (e.g. you pointed the tool at a binary file, or a source file uses
a different encoding). The tool reports this per-file and keeps
analyzing the rest of the batch rather than aborting the whole run.

**Why does it flag things I don't think are actually problems, like
single-letter variable names?**
Every check is a fixed heuristic, not a judgment call informed by
context — that's the trade-off for being deterministic and explainable.
Use `--severity error warning` to hide the more opinionated `info`-level
findings (like `non-descriptive-name` and `missing-docstring`) and focus
on the checks closer to actual bugs.

**Why didn't it catch an obvious duplicate function?**
`duplicate-code` only compares function *bodies* of at least
`MIN_DUPLICATE_STATEMENTS` (3) statements, and matches structurally
(same control flow/operations after stripping names and literals) — two
very short functions, or two functions that do the same thing via
different control flow (e.g. a loop vs. a comprehension), won't be
flagged as duplicates.

**Does it call an LLM or send my code anywhere?**
No. Everything runs locally using Python's built-in `ast` module — no
network access, no API keys, no third-party dependencies.

## License

MIT — see [LICENSE](LICENSE).
