# Contributing

Thanks for looking at improving the AI Code Reviewer. This project is
intentionally simple: a single-file, dependency-free, `ast`-based static
analyzer. Please keep it that way — no LLM calls, no network access, no
third-party dependencies.

## Running the tests

```bash
python3 -m unittest discover -s tests -v
```

CI also runs the analyzer against the bundled `samples/messy_sample.py`
as a smoke test — make sure that still produces findings in every
category if you touch a check.

## Code style

- Every check lives as its own `check_*` method on `FileAnalyzer`, or a
  free function if it doesn't need per-file state (see
  `compute_complexity`, `max_nesting_depth`, `find_duplicate_functions`).
- A `Finding` always has a concrete `message` (what was found) and a
  concrete `suggestion` (what to do about it) — avoid vague wording like
  "consider improving this."
- New checks should default to a reasonable severity (`error` for things
  that are close to bugs, e.g. mutable defaults or bare excepts;
  `warning`/`info` for style and maintainability concerns).
- Keep everything in the standard library (`ast`, `argparse`, `os`,
  `dataclasses`, `collections`). No new dependencies.

## Adding a new check

1. Add the detection logic as a `check_*` method (or helper function for
   anything that doesn't need `self`).
2. Wire it into `FileAnalyzer.analyze()` or `_Visitor` as appropriate.
3. Add a row to the "Checks performed" table in `README.md`.
4. Add both a true-positive and a true-negative unit test in
   `tests/test_review.py`, following the existing per-check `TestX`
   class pattern.
5. Consider adding a triggering snippet to `samples/messy_sample.py` so
   the end-to-end test and example output stay representative.

## Submitting changes

1. Fork the repo and create a branch for your change.
2. Run the full test suite locally and make sure it's green.
3. Open a pull request describing the check or fix and why it's useful.
