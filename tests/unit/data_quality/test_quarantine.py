"""Unit tests for the quarantine write function."""

import os

import pytest
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

from src.data_quality.quarantine import write_to_quarantine

_SCHEMA = StructType(
    [
        StructField("id", IntegerType()),
        StructField("name", StringType()),
        StructField("__error_reason__", StringType()),
    ]
)


class TestWriteToQuarantine:
    def test_writes_records_to_local_path(self, spark, tmp_path):
        df = spark.createDataFrame([(1, "bad_row", "null id")], schema=_SCHEMA)
        base = str(tmp_path)
        write_to_quarantine(df, base, "products", "exec-001", "2025-04-01")
        expected_prefix = os.path.join(base, "table=products", "date=2025-04-01")
        assert os.path.exists(expected_prefix)

    def test_returns_record_count(self, spark, tmp_path):
        df = spark.createDataFrame(
            [(1, "bad", "reason1"), (2, "worse", "reason2")], schema=_SCHEMA
        )
        count = write_to_quarantine(df, str(tmp_path), "orders", "exec-002", "2025-04-02")
        assert count == 2

    def test_empty_df_returns_zero_and_skips_write(self, spark, tmp_path):
        df = spark.createDataFrame([], schema=_SCHEMA)
        count = write_to_quarantine(df, str(tmp_path), "products", "exec-003", "2025-04-01")
        assert count == 0

    def test_sanitises_colon_in_execution_id(self, spark, tmp_path):
        df = spark.createDataFrame([(1, "bad", "reason")], schema=_SCHEMA)
        exec_id = "arn:aws:states:us-east-1:123456789012:execution:pipeline:abc"
        write_to_quarantine(df, str(tmp_path), "products", exec_id, "2025-04-01")
        exec_dir = os.path.join(str(tmp_path), "table=products", "date=2025-04-01")
        # The execution_id subdirectory must not contain colons
        subdirs = os.listdir(exec_dir)
        assert all(":" not in d for d in subdirs)

    def test_written_parquet_is_readable(self, spark, tmp_path):
        df = spark.createDataFrame([(99, "invalid", "test error")], schema=_SCHEMA)
        write_to_quarantine(df, str(tmp_path), "order_items", "exec-004", "2025-04-05")
        read_back = spark.read.parquet(str(tmp_path))
        assert read_back.count() == 1
        assert read_back.first()["id"] == 99

    def test_append_mode_does_not_overwrite(self, spark, tmp_path):
        df1 = spark.createDataFrame([(1, "bad1", "reason1")], schema=_SCHEMA)
        df2 = spark.createDataFrame([(2, "bad2", "reason2")], schema=_SCHEMA)
        base = str(tmp_path)
        write_to_quarantine(df1, base, "products", "exec-005", "2025-04-01")
        write_to_quarantine(df2, base, "products", "exec-005", "2025-04-01")
        total = spark.read.parquet(base).count()
        assert total == 2
