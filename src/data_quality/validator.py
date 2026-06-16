"""Orchestrates data quality rules and produces a ValidationResult."""

import logging

import pyspark.sql.functions as F
from pyspark.sql import DataFrame
from pyspark.sql.types import StringType

from src.data_quality.models import RuleResult, ValidationResult
from src.data_quality.rules import ValidationRule

_ERROR_COL = "__error_reason__"

logger = logging.getLogger(__name__)


class DataQualityValidator:
    """Chains validation rules sequentially; each rule sees only what prior rules passed."""

    def __init__(self, rules: list[ValidationRule], job_logger: logging.Logger | None = None) -> None:
        self._rules = rules
        self._log = job_logger or logger

    def validate(self, df: DataFrame) -> ValidationResult:
        """Apply all rules to df and return a ValidationResult with valid/invalid splits."""
        total = df.count()
        current_valid = df
        all_invalid: list[DataFrame] = []
        rule_results: list[RuleResult] = []

        for rule in self._rules:
            valid, invalid = rule.validate(current_valid)
            failed_count = invalid.count()

            rule_results.append(
                RuleResult(
                    rule_name=rule.rule_name,
                    passed=(failed_count == 0),
                    records_failed=failed_count,
                    error_column=rule.rule_name.split(":")[-1],
                    error_message=f"{failed_count} record(s) failed rule '{rule.rule_name}'",
                )
            )
            self._log.debug(
                "Rule applied",
                extra={"rule": rule.rule_name, "failed": failed_count},
            )
            current_valid = valid
            if failed_count > 0:
                all_invalid.append(invalid)

        records_failed = sum(r.records_failed for r in rule_results)
        records_passed = total - records_failed
        failure_ratio = records_failed / total if total > 0 else 0.0

        invalid_df = self._union_invalid(df, all_invalid)

        self._log.info(
            "Validation complete",
            extra={
                "total_records": total,
                "records_passed": records_passed,
                "records_failed": records_failed,
                "failure_ratio": round(failure_ratio, 4),
            },
        )
        return ValidationResult(
            total_records=total,
            records_passed=records_passed,
            records_failed=records_failed,
            failure_ratio=failure_ratio,
            rule_results=rule_results,
            valid_df=current_valid,
            invalid_df=invalid_df,
        )

    @staticmethod
    def _union_invalid(original_df: DataFrame, invalid_dfs: list[DataFrame]) -> DataFrame:
        """Union all invalid DataFrames; return an empty schema-compatible DF when none exist."""
        if not invalid_dfs:
            return original_df.limit(0).withColumn(
                _ERROR_COL, F.lit(None).cast(StringType())
            )
        result = invalid_dfs[0]
        for frame in invalid_dfs[1:]:
            result = result.union(frame)
        return result
