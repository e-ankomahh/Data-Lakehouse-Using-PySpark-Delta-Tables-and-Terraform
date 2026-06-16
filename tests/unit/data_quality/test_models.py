"""Unit tests for ValidationResult and RuleResult dataclasses."""

import pytest

from src.data_quality.models import RuleResult, ValidationResult


class TestRuleResult:
    def test_stores_all_fields(self):
        r = RuleResult(
            rule_name="not_null:order_id",
            passed=False,
            records_failed=5,
            error_column="order_id",
            error_message="null value in required column 'order_id'",
        )
        assert r.rule_name == "not_null:order_id"
        assert r.passed is False
        assert r.records_failed == 5

    def test_passed_true_when_no_failures(self):
        r = RuleResult(
            rule_name="not_null:id",
            passed=True,
            records_failed=0,
            error_column="id",
            error_message="",
        )
        assert r.passed is True
        assert r.records_failed == 0


class TestValidationResult:
    def _make(self, records_failed=0) -> ValidationResult:
        return ValidationResult(
            total_records=100,
            records_passed=100 - records_failed,
            records_failed=records_failed,
            failure_ratio=records_failed / 100,
        )

    def test_passed_when_no_failures(self):
        assert self._make(records_failed=0).passed is True

    def test_not_passed_when_failures_exist(self):
        assert self._make(records_failed=3).passed is False

    def test_failure_ratio_stored_correctly(self):
        vr = self._make(records_failed=10)
        assert vr.failure_ratio == pytest.approx(0.10)

    def test_default_rule_results_is_empty_list(self):
        vr = self._make()
        assert vr.rule_results == []

    def test_accepts_rule_results(self):
        rule = RuleResult("not_null:x", True, 0, "x", "")
        vr = ValidationResult(
            total_records=10,
            records_passed=10,
            records_failed=0,
            failure_ratio=0.0,
            rule_results=[rule],
        )
        assert len(vr.rule_results) == 1
        assert vr.rule_results[0].rule_name == "not_null:x"
