"""Unit tests for all six data quality validation rules."""

from datetime import datetime

import pytest
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from src.data_quality.rules import (
    BooleanFlagRule,
    NotNullRule,
    PositiveAmountRule,
    ReferentialIntegrityRule,
    TimestampRangeRule,
    UniqueKeyRule,
)

_ERROR_COL = "__error_reason__"


# ---------------------------------------------------------------------------
# Test NotNullRule
# ---------------------------------------------------------------------------
class TestNotNullRule:
    _SCHEMA = StructType(
        [StructField("id", IntegerType()), StructField("name", StringType())]
    )

    def test_rule_name(self):
        assert NotNullRule("id").rule_name == "not_null:id"

    def test_null_rows_go_to_invalid(self, spark):
        df = spark.createDataFrame([(1, "Alice"), (None, "Bob")], schema=self._SCHEMA)
        valid, invalid = NotNullRule("id").validate(df)
        assert valid.count() == 1
        assert invalid.count() == 1

    def test_error_reason_column_present_on_invalid(self, spark):
        df = spark.createDataFrame([(None, "X")], schema=self._SCHEMA)
        _, invalid = NotNullRule("id").validate(df)
        assert _ERROR_COL in invalid.columns

    def test_no_nulls_produces_empty_invalid(self, spark):
        df = spark.createDataFrame([(1, "A"), (2, "B")], schema=self._SCHEMA)
        valid, invalid = NotNullRule("id").validate(df)
        assert valid.count() == 2
        assert invalid.count() == 0

    def test_all_null_produces_empty_valid(self, spark):
        df = spark.createDataFrame([(None, "A")], schema=self._SCHEMA)
        valid, invalid = NotNullRule("id").validate(df)
        assert valid.count() == 0
        assert invalid.count() == 1


# ---------------------------------------------------------------------------
# Test UniqueKeyRule
# ---------------------------------------------------------------------------
class TestUniqueKeyRule:
    _SCHEMA = StructType(
        [StructField("id", IntegerType()), StructField("val", StringType())]
    )

    def test_rule_name(self):
        assert "unique_key" in UniqueKeyRule(["id"]).rule_name

    def test_duplicates_quarantined(self, spark):
        df = spark.createDataFrame([(1, "A"), (1, "B"), (2, "C")], schema=self._SCHEMA)
        valid, invalid = UniqueKeyRule(["id"]).validate(df)
        assert valid.count() == 2
        assert invalid.count() == 1

    def test_no_duplicates_produces_empty_invalid(self, spark):
        df = spark.createDataFrame([(1, "A"), (2, "B")], schema=self._SCHEMA)
        valid, invalid = UniqueKeyRule(["id"]).validate(df)
        assert valid.count() == 2
        assert invalid.count() == 0

    def test_error_reason_on_duplicate(self, spark):
        df = spark.createDataFrame([(1, "A"), (1, "B")], schema=self._SCHEMA)
        _, invalid = UniqueKeyRule(["id"]).validate(df)
        assert _ERROR_COL in invalid.columns

    def test_composite_key_deduplication(self, spark):
        schema = StructType(
            [StructField("a", IntegerType()), StructField("b", IntegerType())]
        )
        df = spark.createDataFrame([(1, 1), (1, 1), (1, 2)], schema=schema)
        valid, invalid = UniqueKeyRule(["a", "b"]).validate(df)
        assert valid.count() == 2
        assert invalid.count() == 1


# ---------------------------------------------------------------------------
# Test ReferentialIntegrityRule
# ---------------------------------------------------------------------------
class TestReferentialIntegrityRule:
    _ORDER_SCHEMA = StructType([StructField("order_id", IntegerType())])
    _ITEM_SCHEMA = StructType(
        [StructField("id", IntegerType()), StructField("order_id", IntegerType())]
    )

    def test_rule_name(self, spark):
        ref = spark.createDataFrame([(1,)], schema=self._ORDER_SCHEMA)
        assert "referential_integrity" in ReferentialIntegrityRule("order_id", ref, "order_id").rule_name

    def test_orphaned_rows_quarantined(self, spark):
        ref = spark.createDataFrame([(1,), (2,)], schema=self._ORDER_SCHEMA)
        items = spark.createDataFrame([(10, 1), (11, 99)], schema=self._ITEM_SCHEMA)
        valid, invalid = ReferentialIntegrityRule("order_id", ref, "order_id").validate(items)
        assert valid.count() == 1
        assert invalid.count() == 1

    def test_all_valid_produces_empty_invalid(self, spark):
        ref = spark.createDataFrame([(1,), (2,)], schema=self._ORDER_SCHEMA)
        items = spark.createDataFrame([(10, 1), (11, 2)], schema=self._ITEM_SCHEMA)
        valid, invalid = ReferentialIntegrityRule("order_id", ref, "order_id").validate(items)
        assert valid.count() == 2
        assert invalid.count() == 0

    def test_error_reason_on_orphan(self, spark):
        ref = spark.createDataFrame([(1,)], schema=self._ORDER_SCHEMA)
        items = spark.createDataFrame([(10, 999)], schema=self._ITEM_SCHEMA)
        _, invalid = ReferentialIntegrityRule("order_id", ref, "order_id").validate(items)
        assert _ERROR_COL in invalid.columns


# ---------------------------------------------------------------------------
# Test TimestampRangeRule
# ---------------------------------------------------------------------------
class TestTimestampRangeRule:
    _SCHEMA = StructType(
        [StructField("id", IntegerType()), StructField("ts", TimestampType())]
    )
    _MIN = datetime(2020, 1, 1)
    _MAX = datetime(2030, 12, 31)

    def test_rule_name(self):
        assert "timestamp_range" in TimestampRangeRule("ts", self._MIN, self._MAX).rule_name

    def test_out_of_range_rows_quarantined(self, spark):
        df = spark.createDataFrame(
            [(1, datetime(2025, 6, 1)), (2, datetime(2015, 1, 1))],
            schema=self._SCHEMA,
        )
        valid, invalid = TimestampRangeRule("ts", self._MIN, self._MAX).validate(df)
        assert valid.count() == 1
        assert invalid.count() == 1

    def test_all_in_range_produces_empty_invalid(self, spark):
        df = spark.createDataFrame(
            [(1, datetime(2024, 3, 15)), (2, datetime(2026, 7, 4))],
            schema=self._SCHEMA,
        )
        valid, invalid = TimestampRangeRule("ts", self._MIN, self._MAX).validate(df)
        assert valid.count() == 2
        assert invalid.count() == 0


# ---------------------------------------------------------------------------
# Test PositiveAmountRule
# ---------------------------------------------------------------------------
class TestPositiveAmountRule:
    _SCHEMA = StructType(
        [StructField("id", IntegerType()), StructField("amount", DoubleType())]
    )

    def test_rule_name(self):
        assert "positive_amount" in PositiveAmountRule("amount").rule_name

    def test_zero_amount_quarantined(self, spark):
        df = spark.createDataFrame([(1, 0.0), (2, 5.0)], schema=self._SCHEMA)
        valid, invalid = PositiveAmountRule("amount").validate(df)
        assert valid.count() == 1
        assert invalid.count() == 1

    def test_negative_amount_quarantined(self, spark):
        df = spark.createDataFrame([(1, -1.0)], schema=self._SCHEMA)
        valid, invalid = PositiveAmountRule("amount").validate(df)
        assert valid.count() == 0
        assert invalid.count() == 1

    def test_positive_amount_passes(self, spark):
        df = spark.createDataFrame([(1, 99.99)], schema=self._SCHEMA)
        valid, invalid = PositiveAmountRule("amount").validate(df)
        assert valid.count() == 1
        assert invalid.count() == 0


# ---------------------------------------------------------------------------
# Test BooleanFlagRule
# ---------------------------------------------------------------------------
class TestBooleanFlagRule:
    _SCHEMA = StructType(
        [StructField("id", IntegerType()), StructField("flag", IntegerType())]
    )

    def test_rule_name(self):
        assert "boolean_flag" in BooleanFlagRule("flag").rule_name

    def test_value_2_quarantined(self, spark):
        df = spark.createDataFrame([(1, 0), (2, 1), (3, 2)], schema=self._SCHEMA)
        valid, invalid = BooleanFlagRule("flag").validate(df)
        assert valid.count() == 2
        assert invalid.count() == 1

    def test_zero_and_one_pass(self, spark):
        df = spark.createDataFrame([(1, 0), (2, 1)], schema=self._SCHEMA)
        valid, invalid = BooleanFlagRule("flag").validate(df)
        assert valid.count() == 2
        assert invalid.count() == 0

    def test_error_reason_on_invalid_flag(self, spark):
        df = spark.createDataFrame([(1, 99)], schema=self._SCHEMA)
        _, invalid = BooleanFlagRule("flag").validate(df)
        assert _ERROR_COL in invalid.columns
