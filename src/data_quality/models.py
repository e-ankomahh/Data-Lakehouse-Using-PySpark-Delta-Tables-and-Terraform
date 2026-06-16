"""Dataclasses representing per-rule and overall validation outcomes."""

from dataclasses import dataclass, field

from pyspark.sql import DataFrame


@dataclass
class RuleResult:
    """Outcome for a single validation rule applied to a DataFrame."""

    rule_name: str
    passed: bool
    records_failed: int
    error_column: str
    error_message: str


@dataclass
class ValidationResult:
    """Aggregate outcome returned by DataQualityValidator.validate()."""

    total_records: int
    records_passed: int
    records_failed: int
    failure_ratio: float
    rule_results: list[RuleResult] = field(default_factory=list)
    valid_df: DataFrame = field(default=None)
    invalid_df: DataFrame = field(default=None)

    @property
    def passed(self) -> bool:
        """True when every individual rule passed (no records quarantined)."""
        return self.records_failed == 0
