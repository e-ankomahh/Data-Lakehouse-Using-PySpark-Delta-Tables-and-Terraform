"""Unit tests for Delta Lake utility functions using a local SparkSession."""

import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

from src.lib.delta_utils import (
    MergeResult,
    create_delta_table_if_not_exists,
    get_delta_table_version,
    read_delta_table,
    write_delta_table_merge,
)
from src.lib.exceptions import DeltaMergeError

_SIMPLE_SCHEMA = StructType(
    [
        StructField("id", IntegerType(), nullable=False),
        StructField("name", StringType(), nullable=True),
    ]
)


def _make_df(spark: SparkSession, rows: list[tuple]):
    """Helper to build a small DataFrame with _SIMPLE_SCHEMA."""
    return spark.createDataFrame(rows, schema=_SIMPLE_SCHEMA)


class TestMergeResult:
    def test_total_affected_sums_all_counts(self):
        r = MergeResult(rows_inserted=3, rows_updated=2, rows_unchanged=10)
        assert r.total_affected == 15

    def test_zero_counts(self):
        r = MergeResult(rows_inserted=0, rows_updated=0, rows_unchanged=0)
        assert r.total_affected == 0


class TestCreateDeltaTableIfNotExists:
    def test_creates_table_when_missing(self, spark, tmp_path):
        path = str(tmp_path / "products")
        create_delta_table_if_not_exists(spark, _SIMPLE_SCHEMA, path, [])
        # Table must be readable
        df = spark.read.format("delta").load(path)
        assert df.count() == 0

    def test_idempotent_when_table_exists(self, spark, tmp_path):
        path = str(tmp_path / "idempotent")
        create_delta_table_if_not_exists(spark, _SIMPLE_SCHEMA, path, [])
        # Call again — must not raise
        create_delta_table_if_not_exists(spark, _SIMPLE_SCHEMA, path, [])
        df = spark.read.format("delta").load(path)
        assert df.count() == 0

    def test_creates_table_with_partition_columns(self, spark, tmp_path):
        schema = StructType(
            [
                StructField("id", IntegerType(), nullable=False),
                StructField("date", StringType(), nullable=True),
            ]
        )
        path = str(tmp_path / "partitioned")
        create_delta_table_if_not_exists(spark, schema, path, ["date"])
        df = spark.read.format("delta").load(path)
        assert df.count() == 0


class TestWriteDeltaTableMerge:
    def _create_table(self, spark: SparkSession, path: str) -> None:
        create_delta_table_if_not_exists(spark, _SIMPLE_SCHEMA, path, [])

    def test_inserts_new_rows(self, spark, tmp_path):
        path = str(tmp_path / "insert_test")
        self._create_table(spark, path)
        df = _make_df(spark, [(1, "Alice"), (2, "Bob")])
        result = write_delta_table_merge(spark, df, path, merge_keys=["id"])
        assert isinstance(result, MergeResult)
        assert result.rows_inserted == 2

    def test_updates_existing_rows(self, spark, tmp_path):
        path = str(tmp_path / "update_test")
        self._create_table(spark, path)
        # First insert
        write_delta_table_merge(spark, _make_df(spark, [(1, "Alice")]), path, ["id"])
        # Update
        result = write_delta_table_merge(
            spark, _make_df(spark, [(1, "AliceUpdated")]), path, ["id"]
        )
        assert result.rows_updated == 1
        out = spark.read.format("delta").load(path)
        assert out.filter("id = 1").first()["name"] == "AliceUpdated"

    def test_mixed_insert_and_update(self, spark, tmp_path):
        path = str(tmp_path / "mixed_test")
        self._create_table(spark, path)
        write_delta_table_merge(spark, _make_df(spark, [(1, "Alice")]), path, ["id"])
        df = _make_df(spark, [(1, "AliceV2"), (2, "Bob")])
        result = write_delta_table_merge(spark, df, path, ["id"])
        assert result.rows_updated == 1
        assert result.rows_inserted == 1

    def test_raises_delta_merge_error_on_bad_path(self, spark, tmp_path):
        non_existent = str(tmp_path / "does_not_exist")
        df = _make_df(spark, [(1, "Alice")])
        with pytest.raises(DeltaMergeError):
            write_delta_table_merge(spark, df, non_existent, ["id"])

    def test_idempotent_rerun_produces_no_inserts(self, spark, tmp_path):
        path = str(tmp_path / "idempotent_merge")
        self._create_table(spark, path)
        df = _make_df(spark, [(1, "Alice")])
        write_delta_table_merge(spark, df, path, ["id"])
        result = write_delta_table_merge(spark, df, path, ["id"])
        assert result.rows_inserted == 0


class TestReadDeltaTable:
    def test_reads_written_data_correctly(self, spark, tmp_path):
        path = str(tmp_path / "read_test")
        create_delta_table_if_not_exists(spark, _SIMPLE_SCHEMA, path, [])
        write_delta_table_merge(spark, _make_df(spark, [(99, "Test")]), path, ["id"])
        df = read_delta_table(spark, path)
        assert df.count() == 1
        assert df.first()["id"] == 99


class TestGetDeltaTableVersion:
    def test_version_increments_on_each_write(self, spark, tmp_path):
        path = str(tmp_path / "version_test")
        create_delta_table_if_not_exists(spark, _SIMPLE_SCHEMA, path, [])
        v0 = get_delta_table_version(spark, path)
        write_delta_table_merge(spark, _make_df(spark, [(1, "A")]), path, ["id"])
        v1 = get_delta_table_version(spark, path)
        assert v1 == v0 + 1
