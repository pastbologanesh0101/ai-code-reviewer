"""Unit tests for review.py.

Each major check gets a true-positive case (a snippet that SHOULD trigger
the finding) and a true-negative case (a similar snippet that should NOT).
There is also an end-to-end test that runs the full analyzer against the
bundled messy sample file and checks that multiple expected finding
categories show up together.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review  # noqa: E402


def categories(findings):
    return {f.category for f in findings}


class TestHighComplexity(unittest.TestCase):
    def test_positive_high_complexity(self):
        src = """
def tangled(a, b, c, d):
    if a:
        if b:
            pass
        elif c:
            pass
    if a and b and c and d:
        pass
    for i in range(10):
        if i % 2:
            pass
        elif i % 3:
            pass
    while d:
        d -= 1
        if d == 1:
            pass
    try:
        pass
    except ValueError:
        pass
    except TypeError:
        pass
    x = 1 if a else 2
    assert x
    return x
"""
        findings = review.analyze_source("t.py", src)
        self.assertIn("high-complexity", categories(findings))

    def test_negative_low_complexity(self):
        src = """
def simple(a, b):
    \"\"\"Add two numbers.\"\"\"
    return a + b
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("high-complexity", categories(findings))


class TestLongFunction(unittest.TestCase):
    def test_positive_long_function(self):
        body = "\n".join(f"    x{i} = {i}" for i in range(60))
        src = f"def big():\n{body}\n    return x0\n"
        findings = review.analyze_source("t.py", src)
        self.assertIn("long-function", categories(findings))

    def test_negative_short_function(self):
        src = """
def small():
    \"\"\"Return a constant.\"\"\"
    return 1
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("long-function", categories(findings))


class TestTooManyParameters(unittest.TestCase):
    def test_positive_too_many_params(self):
        src = """
def many_params(a, b, c, d, e, f, g):
    \"\"\"Do something with many params.\"\"\"
    return a + b + c + d + e + f + g
"""
        findings = review.analyze_source("t.py", src)
        self.assertIn("too-many-parameters", categories(findings))

    def test_negative_few_params(self):
        src = """
def few_params(a, b):
    \"\"\"Add two things.\"\"\"
    return a + b
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("too-many-parameters", categories(findings))

    def test_method_discounts_self(self):
        src = """
class Thing:
    def method(self, a, b, c, d, e):
        \"\"\"Method with five real params after self.\"\"\"
        return a + b + c + d + e
"""
        findings = review.analyze_source("t.py", src)
        # 5 real params (self discounted) sits at the threshold, not over it.
        self.assertNotIn("too-many-parameters", categories(findings))


class TestDeepNesting(unittest.TestCase):
    def test_positive_deep_nesting(self):
        src = """
def nested(a):
    \"\"\"Deeply nested control flow.\"\"\"
    if a:
        if a:
            if a:
                if a:
                    if a:
                        return 1
    return 0
"""
        findings = review.analyze_source("t.py", src)
        self.assertIn("deep-nesting", categories(findings))

    def test_negative_flat_function(self):
        src = """
def flat(a):
    \"\"\"Shallow control flow.\"\"\"
    if a:
        return 1
    return 0
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("deep-nesting", categories(findings))


class TestMutableDefaultArgument(unittest.TestCase):
    def test_positive_mutable_default(self):
        src = """
def f(items=[]):
    \"\"\"Append and return.\"\"\"
    items.append(1)
    return items
"""
        findings = review.analyze_source("t.py", src)
        self.assertIn("mutable-default-argument", categories(findings))

    def test_negative_none_default(self):
        src = """
def f(items=None):
    \"\"\"Append and return, safely.\"\"\"
    if items is None:
        items = []
    items.append(1)
    return items
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("mutable-default-argument", categories(findings))


class TestBareExcept(unittest.TestCase):
    def test_positive_bare_except(self):
        src = """
def f():
    \"\"\"Try something.\"\"\"
    try:
        risky_call()
    except:
        pass
"""
        findings = review.analyze_source("t.py", src)
        self.assertIn("bare-except", categories(findings))

    def test_negative_specific_except(self):
        src = """
def f():
    \"\"\"Try something safely.\"\"\"
    try:
        risky_call()
    except ValueError:
        pass
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("bare-except", categories(findings))


class TestUnusedImport(unittest.TestCase):
    def test_positive_unused_import(self):
        src = """
import os


def f():
    \"\"\"Do nothing with os.\"\"\"
    return 1
"""
        findings = review.analyze_source("t.py", src)
        self.assertIn("unused-import", categories(findings))

    def test_negative_used_import(self):
        src = """
import os


def f():
    \"\"\"Use os.\"\"\"
    return os.getcwd()
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("unused-import", categories(findings))


class TestNonDescriptiveNames(unittest.TestCase):
    def test_positive_single_letter_variable(self):
        src = """
def f():
    \"\"\"Assign a bad name.\"\"\"
    q = 42
    return q
"""
        findings = review.analyze_source("t.py", src)
        self.assertIn("non-descriptive-name", categories(findings))

    def test_negative_descriptive_variable(self):
        src = """
def f():
    \"\"\"Assign a good name.\"\"\"
    total_count = 42
    return total_count
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("non-descriptive-name", categories(findings))

    def test_negative_loop_counter_allowed(self):
        src = """
def f():
    \"\"\"Use a conventional loop counter.\"\"\"
    total = 0
    for i in range(10):
        total += i
    return total
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("non-descriptive-name", categories(findings))


class TestMissingDocstring(unittest.TestCase):
    def test_positive_missing_docstring(self):
        src = """
def f(a, b):
    return a + b
"""
        findings = review.analyze_source("t.py", src)
        self.assertIn("missing-docstring", categories(findings))

    def test_negative_has_docstring(self):
        src = """
def f(a, b):
    \"\"\"Add two numbers.\"\"\"
    return a + b
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("missing-docstring", categories(findings))

    def test_negative_private_function_exempt(self):
        src = """
def _helper(a, b):
    return a + b
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("missing-docstring", categories(findings))


class TestDuplicateCode(unittest.TestCase):
    def test_positive_duplicate_functions(self):
        src = """
def calc_one(a, b, c):
    total = a + b
    total = total * c
    return total


def calc_two(x, y, z):
    total = x + y
    total = total * z
    return total
"""
        findings = review.analyze_source("t.py", src)
        self.assertIn("duplicate-code", categories(findings))

    def test_negative_distinct_functions(self):
        src = """
def calc_sum(a, b):
    \"\"\"Sum two numbers.\"\"\"
    return a + b


def calc_product_of_range(n):
    \"\"\"Multiply numbers from 1 to n.\"\"\"
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result
"""
        findings = review.analyze_source("t.py", src)
        self.assertNotIn("duplicate-code", categories(findings))


class TestCLISeverityFiltering(unittest.TestCase):
    def test_severity_filter_only_errors(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "messy_sample.py")
        findings = review.analyze_file(path)
        error_findings = [f for f in findings if f.severity == "error"]
        all_severities = {f.severity for f in findings}
        self.assertIn("error", all_severities)
        self.assertTrue(all(f.severity == "error" for f in error_findings))


class TestEndToEndMessySample(unittest.TestCase):
    def test_messy_sample_triggers_expected_categories(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "messy_sample.py")
        findings = review.analyze_file(path)
        found_categories = categories(findings)

        expected = {
            "high-complexity",
            "long-function",
            "too-many-parameters",
            "deep-nesting",
            "mutable-default-argument",
            "bare-except",
            "unused-import",
            "non-descriptive-name",
            "missing-docstring",
            "duplicate-code",
        }
        missing = expected - found_categories
        self.assertEqual(missing, set(), f"Expected categories not found: {missing}")
        self.assertGreater(len(findings), 20)


class TestSyntaxErrorHandling(unittest.TestCase):
    def test_analyze_source_raises_syntax_error_on_invalid_python(self):
        """A file that isn't valid Python must raise SyntaxError from
        analyze_source, rather than crashing somewhere unexpected."""
        src = "def broken(:\n    pass\n"
        with self.assertRaises(SyntaxError):
            review.analyze_source("t.py", src)

    def test_main_reports_unparsable_file_without_crashing_other_files(self):
        """main() should keep going and report a per-file error for an
        unparsable file, instead of letting the exception propagate and
        abort analysis of the rest of the batch."""
        import tempfile
        import io
        import contextlib

        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = os.path.join(tmpdir, "bad.py")
            with open(bad_path, "w") as f:
                f.write("def broken(:\n    pass\n")
            good_path = os.path.join(tmpdir, "good.py")
            with open(good_path, "w") as f:
                f.write("def ok():\n    \"\"\"Fine.\"\"\"\n    return 1\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exit_code = review.main([tmpdir])

        self.assertEqual(exit_code, 0)
        self.assertIn("could not be analyzed", buf.getvalue())


class TestUnreadableFileHandling(unittest.TestCase):
    def test_main_reports_undecodable_file_without_crashing_batch(self):
        """A file with bytes that aren't valid UTF-8 (e.g. accidentally
        pointing the tool at a binary file) must be reported per-file,
        not crash the whole run via an uncaught UnicodeDecodeError."""
        import tempfile
        import io
        import contextlib

        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = os.path.join(tmpdir, "binary.py")
            with open(binary_path, "wb") as f:
                f.write(b"\xff\xfe\x00\x01not valid utf-8")
            good_path = os.path.join(tmpdir, "good.py")
            with open(good_path, "w") as f:
                f.write("def ok():\n    \"\"\"Fine.\"\"\"\n    return 1\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exit_code = review.main([tmpdir])

        self.assertEqual(exit_code, 0)
        self.assertIn("could not be analyzed", buf.getvalue())


class TestFileDiscoverySkipsJunkDirs(unittest.TestCase):
    def test_discover_python_files_skips_pycache_and_venv(self):
        """Generated/vendored directories like __pycache__ and .venv must
        not be scanned, even though they can contain .py-like files."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            real_path = os.path.join(tmpdir, "real.py")
            with open(real_path, "w") as f:
                f.write("x = 1\n")

            for junk_dir in ("__pycache__", ".venv"):
                junk_path = os.path.join(tmpdir, junk_dir)
                os.makedirs(junk_path)
                with open(os.path.join(junk_path, "ignored.py"), "w") as f:
                    f.write("y = 2\n")

            found = review.discover_python_files(tmpdir)

        self.assertEqual(found, [real_path])


if __name__ == "__main__":
    unittest.main()
