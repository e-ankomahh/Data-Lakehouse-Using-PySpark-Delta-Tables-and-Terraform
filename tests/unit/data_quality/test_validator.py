"""Unit tests for DataQualityValidator orchestration logic."""

import pytest
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

from src.data_quality.models import ValidationResult
from src.data_quality.rules import NotNullRule, PositiveAmountRule, UniqueKeyRule
from src.data_quality.validator import DataQualityValidator

_SCHEMA = StructType(
    [
        StructField("id", IntegerType()),
        StructField("name", StringType()),
    ]
)

_AMT_SCHEMA = StructType(
    [
        StructField("id", IntegerType()),
        StructField("amount", IntegerType()),
    ]
)


class TestDataQualityValidatorNoRules:
    def test_no_rules_all_records_pass(self, spark):
        df = spark.createDataFrame([(1, "A"), (2, "B")], schema=_SCHEMA)
        result = DataQualityValidator([]).validate(df)
        assert result.total_records == 2
        assert result.records_passed == 2
        assert result.records_failed == 0
        assert result.passed is True

    def test_no_rules_empty_invalid_df(self, spark):
        df = spark.createDataFrame([(1, "A")], schema=_SCHEMA)
        result = DataQualityValidator([]).validate(df)
        assert result.invalid_df.count() == 0

    def test_no_rules_valid_df_equals_input(self, spark):
        df = spark.createDataFrame([(1, "A"), (2, "B")], schema=_SCHEMA)
        result = DataQualityValidator([]).validate(df)
        assert result.valid_df.count() == 2


class TestDataQualityValidatorSingleRule:
    def test_not_null_rule_quarantines_nulls(self, spark):
        df = spark.createDataFrame([(1, "A"), (None, "B")], schema=_SCHEMA)
        result = DataQualityValidator([NotNullRule("id")]).validate(df)
        assert result.records_passed == 1
        assert result.records_failed == 1

    def test_failure_ratio_calculated_correctly(self, spark):
        df = spark.createDataFrame([(1, "A"), (None, "B"), (None, "C")], schema=_SCHEMA)
        result = DataQualityValidator([NotNullRule("id")]).validate(df)
        assert result.failure_ratio == pytest.approx(2 / 3)

    def test_returns_validation_result_type(self, spark):
        df = spark.createDataFrame([(1, "A")], schema=_SCHEMA)
        result = DataQualityValidator([NotNullRule("id")]).validate(df)
        assert isinstance(result, ValidationResult)

    def test_rule_result_recorded(self, spark):
        df = spark.createDataFrame([(None, "A")], schema=_SCHEMA)
        result = DataQualityValidator([NotNullRule("id")]).validate(df)
        assert len(result.rule_results) == 1
        assert result.rule_results[0].rule_name == "not_null:id"
        assert result.rule_results[0].passed is False
        assert result.rule_results[0].records_failed == 1


class TestDataQualityValidatorMultipleRules:
    def test_rules_applied_sequentially(self, spark):
        # Row (None, 5): fails NotNull — should NOT be re-evaluated by PositiveAmount
        # Row (1, -1): passes NotNull, fails PositiveAmount
        # Row (2, 10): passes both
        df = spark.createDataFrame([(None, 5), (1, -1), (2, 10)], schema=_AMT_SCHEMA)
        rules = [NotNullRule("id"), PositiveAmountRule("amount")]
        result = DataQualityValidator(rules).validate(df)
        assert result.records_passed == 1
        assert result.records_failed == 2

    def test_invalid_df_contains_all_quarantined_rows(self, spark):
        df = spark.createDataFrame([(None, 5), (1, -1), (2, 10)], schema=_AMT_SCHEMA)
        rules = [NotNullRule("id"), PositiveAmountRule("amount")]
        result = DataQualityValidator(rules).validate(df)
        assert result.invalid_df.count() == 2

    def test_two_rule_results_recorded(self, spark):
        df = spark.createDataFrame([(1, 10)], schema=_AMT_SCHEMA)
        rules = [NotNullRule("id"), PositiveAmountRule("amount")]
        result = DataQualityValidator(rules).validate(df)
        assert len(result.rule_results) == 2

    def test_all_pass_when_data_clean(self, spark):
        df = spark.createDataFrame([(1, "Alice"), (2, "Bob")], schema=_SCHEMA)
        result = DataQualityValidator([NotNullRule("id"), NotNullRule("name")]).validate(df)
        assert result.passed is True
        assert result.failure_ratio == 0.0

    def test_failure_ratio_zero_for_empty_df(self, spark):
        df = spark.createDataFrame([], schema=_SCHEMA)
        result = DataQualityValidator([NotNullRule("id")]).validate(df)
        assert result.failure_ratio == 0.0
        assert result.total_records == 0

    def test_unique_key_followed_by_not_null(self, spark):
        # Rows: (1,A), (1,B) duplicate — one gets quarantined by UniqueKey.
        # Only (None, C) should fail NotNull applied to surviving rows.
        df = spark.createDataFrame([(1, "A"), (1, "B"), (None, "C")], schema=_SCHEMA)
        rules = [UniqueKeyRule(["id"]), NotNullRule("id")]
        result = DataQualityValidator(rules).validate(df)
        # 1 duplicate + 1 null = 2 quarantined, 1 passes
        assert result.records_failed == 2
        assert result.records_passed == 1
