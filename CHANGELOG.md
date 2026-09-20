# Changelog

All notable changes to this project are documented in this file.

## [0.1.0] - Initial release

The first working version of the AI Code Reviewer.

### Added
- `review.py`: a single-file, dependency-free, `ast`-based static
  analyzer for Python source, with no LLM call and no network access.
- Ten checks: `high-complexity` (McCabe cyclomatic complexity),
  `long-function`, `too-many-parameters`, `deep-nesting`,
  `mutable-default-argument`, `bare-except`, `unused-import`,
  `non-descriptive-name`, `missing-docstring`, and `duplicate-code`
  (structural AST-fingerprint matching).
- Each finding includes file, line number, severity (`error` /
  `warning` / `info`), a human-readable message, and a concrete fix
  suggestion.
- CLI supporting single-file or recursive directory analysis, plus
  `--severity` filtering.
- `samples/messy_sample.py`: a deliberately messy file that triggers
  every check, used for documentation examples and as an end-to-end
  test fixture.
- Unit test suite (`tests/test_review.py`) with a true-positive and
  true-negative case for every check, plus an end-to-end test against
  the messy sample.
- GitHub Actions CI running the unit tests and a smoke test of the CLI
  against the messy sample, on Python 3.11 and 3.12.
- MIT license and a README documenting every check and its rationale.
