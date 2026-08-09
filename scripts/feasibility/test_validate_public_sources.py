import unittest

from scripts.feasibility.validate_public_sources import (
    build_summary,
    exit_code_for_status,
    fetch_with_error,
)


class SummaryStatusTests(unittest.TestCase):
    def test_pass_when_all_checks_pass_and_no_gaps(self) -> None:
        summary = build_summary(
            [
                {"check": "required", "status": "PASS", "required": True},
                {"check": "optional", "status": "PASS", "required": False},
            ],
            configuration_gaps=[],
            warnings=[],
        )

        self.assertEqual(summary["overall_status"], "PASS")
        self.assertEqual(exit_code_for_status(summary["overall_status"]), 0)

    def test_partial_when_only_optional_check_fails(self) -> None:
        summary = build_summary(
            [
                {"check": "required", "status": "PASS", "required": True},
                {"check": "optional", "status": "FAIL", "required": False},
            ],
            configuration_gaps=[],
            warnings=[],
        )

        self.assertEqual(summary["overall_status"], "PARTIAL")
        self.assertEqual(exit_code_for_status(summary["overall_status"]), 2)

    def test_blocked_when_required_check_is_blocked(self) -> None:
        summary = build_summary(
            [{"check": "required", "status": "BLOCKED", "required": True}],
            configuration_gaps=["SEC_CONTACT_NOT_CONFIGURED"],
            warnings=[],
        )

        self.assertEqual(summary["overall_status"], "BLOCKED")
        self.assertEqual(exit_code_for_status(summary["overall_status"]), 3)

    def test_fail_when_required_check_fails(self) -> None:
        summary = build_summary(
            [{"check": "required", "status": "FAIL", "required": True}],
            configuration_gaps=[],
            warnings=[],
        )

        self.assertEqual(summary["overall_status"], "FAIL")
        self.assertEqual(exit_code_for_status(summary["overall_status"]), 1)


class FetchIsolationTests(unittest.TestCase):
    def test_fetch_with_error_converts_timeout_to_data(self) -> None:
        class TimeoutReader:
            def fetch(self, url: str, **kwargs: object) -> object:
                raise TimeoutError("read timed out")

        status, headers, raw, error = fetch_with_error(TimeoutReader(), "https://example.invalid")

        self.assertIsNone(status)
        self.assertEqual(headers, {})
        self.assertEqual(raw, b"")
        self.assertEqual(error, "TimeoutError: read timed out")


if __name__ == "__main__":
    unittest.main()
