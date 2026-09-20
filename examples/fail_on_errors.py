#!/usr/bin/env python3
"""Example: use review.py as a library to build a strict CI gate.

review.py's own CLI always exits 0 (it's a reporting tool, not a gate --
see the README). This example shows how to import it as a library and
build a stricter wrapper: exit non-zero if any `error`-severity finding
is present, which is the kind of thing you'd wire into a pre-commit hook
or a CI job that should actually block a merge.

Usage:
    python examples/fail_on_errors.py path/to/file_or_directory
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import review


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: fail_on_errors.py <path>", file=sys.stderr)
        return 2

    target = sys.argv[1]
    if not os.path.exists(target):
        print(f"error: path not found: {target}", file=sys.stderr)
        return 2

    error_count = 0
    for path in review.discover_python_files(target):
        try:
            findings = review.analyze_file(path)
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            print(f"{path}: could not be analyzed ({exc})")
            continue

        errors = [f for f in findings if f.severity == "error"]
        for finding in errors:
            print(finding.format())
        error_count += len(errors)

    if error_count:
        print(f"\nFAIL: {error_count} error-level finding(s).")
        return 1

    print("OK: no error-level findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
