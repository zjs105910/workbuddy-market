import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.private_release_gate import (
    REQUIRE_ENV,
    TERMS_FILE_ENV,
    load_private_terms,
)


class PrivateReleaseGateTests(unittest.TestCase):
    def test_normal_development_allows_absent_local_terms(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_private_terms(Path("does-not-exist")), frozenset())

    def test_protected_release_fails_closed_without_terms_file(self) -> None:
        environment = {REQUIRE_ENV: "1", TERMS_FILE_ENV: "does-not-exist"}
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, TERMS_FILE_ENV):
                load_private_terms()

    def test_protected_release_requires_explicit_external_terms_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fallback = Path(directory) / "local-terms.txt"
            fallback.write_text("local-term\n", encoding="utf-8")
            with patch.dict(os.environ, {REQUIRE_ENV: "1"}, clear=True):
                with self.assertRaisesRegex(RuntimeError, TERMS_FILE_ENV):
                    load_private_terms(fallback)

    def test_protected_release_fails_closed_for_empty_terms_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "terms.txt"
            empty.write_text("# comments do not count\n", encoding="utf-8")
            environment = {REQUIRE_ENV: "1", TERMS_FILE_ENV: str(empty)}
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(RuntimeError, "empty"):
                    load_private_terms()

    def test_configured_terms_are_loaded_without_echoing_their_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            terms = Path(directory) / "terms.txt"
            terms.write_text("first-local-term\n# note\nsecond-local-term\n")
            environment = {REQUIRE_ENV: "1", TERMS_FILE_ENV: str(terms)}
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(
                    load_private_terms(),
                    frozenset({"first-local-term", "second-local-term"}),
                )


if __name__ == "__main__":
    unittest.main()
