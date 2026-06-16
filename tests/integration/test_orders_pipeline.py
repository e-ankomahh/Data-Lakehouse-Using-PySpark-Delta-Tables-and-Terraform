"""Integration tests for the orders ETL pipeline — full stack with injected DataFrames."""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from pyspark.sql import Row

from src.glue_jobs.orders_job import _xlsx_to_spark_df, run
from src.lib.config import config_from_glue_args
from src.lib.delta_utils import read_delta_table
from src.lib.logging_utils import get_logger
from src.lib.schema_definitions import ORDERS_SCHEMA

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

_VALID_ARGS = {
    "JOB_NAME": "integration-orders-job",
    "RAW_BUCKET": "test-raw",
    "PROCESSED_BUCKET": "test-processed",
    "QUARANTINE_BUCKET": "test-quarantine",
    "ARCHIVE_BUCKET": "test-archive",
    "ENVIRONMENT": "test",
}

_SAMPLE_ROWS = [
    Row(order_num=1, order_id=101, user_id=11, order_timestamp=datetime(2025, 4, 1, 8, 15),
        total_amount=34.50, date=date(2025, 4, 1)),
    Row(order_num=2, order_id=102, user_id=12, order_timestamp=datetime(2025, 4, 2, 9, 30),
        total_amount=17.99, date=date(2025, 4, 2)),
    Row(order_num=3, order_id=103, user_id=13, order_timestamp=datetime(2025, 4, 3, 11, 0),
        total_amount=52.10, date=date(2025, 4, 3)),
    Row(order_num=4, order_id=104, user_id=14, order_timestamp=datetime(2025, 4, 4, 13, 45),
        total_amount=8.75, date=date(2025, 4, 4)),
    Row(order_num=5, order_id=105, user_id=15, order_timestamp=datetime(2025, 4, 5, 16, 20),
        total_amount=99.00, date=date(2025, 4, 5)),
]


@pytest.fixture
def cfg():
    return config_from_glue_args(_VALID_ARGS)


@pytest.fixture
def log(cfg):
    return get_logger("orders", cfg.job_name, "integration-orders-exec-001", cfg.environment)


@pytest.fixture
def sample_df(spark):
    return spark.createDataFrame(_SAMPLE_ROWS, schema=ORDERS_SCHEMA)


@patch("src.glue_jobs.orders_job.emit_job_metrics")
class TestOrdersPipelineIntegration:
    def test_full_run_inserts_all_valid_rows(self, _m, spark, cfg, log, sample_df, tmp_path):
        result = run(spark, cfg, log, source_df=sample_df, delta_path=str(tmp_path / "delta"),
                     quarantine_base_path=str(tmp_path / "q"))
        assert result["total"] == 5
        assert result["inserted"] == 5
        assert result["rejected"] == 0

    def test_delta_table_readable_after_run(self, _m, spark, cfg, log, sample_df, tmp_path):
        delta = str(tmp_path / "delta_read")
        run(spark, cfg, log, source_df=sample_df, delta_path=delta,
            quarantine_base_path=str(tmp_path / "q"))
        df = read_delta_table(spark, delta)
        assert df.count() == 5
        assert set(df.columns) == {"order_num", "order_id", "user_id",
                                    "order_timestamp", "total_amount", "date"}

    def test_two_runs_are_idempotent(self, _m, spark, cfg, log, sample_df, tmp_path):
        delta = str(tmp_path / "delta_idem")
        q = str(tmp_path / "q_idem")
        run(spark, cfg, log, source_df=sample_df, delta_path=delta, quarantine_base_path=q)
        result = run(spark, cfg, log, source_df=sample_df, delta_path=delta, quarantine_base_path=q)
        assert result["inserted"] == 0
        assert read_delta_table(spark, delta).count() == 5

    def test_xlsx_bridge_produces_readable_dataframe(self, _m, spark, tmp_path):
        """Verify the pandas bridge with a real openpyxl-written XLSX file."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["order_num", "order_id", "user_id", "order_timestamp", "total_amount", "date"])
        for row in _SAMPLE_ROWS:
            ws.append([row.order_num, row.order_id, row.user_id,
                       row.order_timestamp, row.total_amount, row.date])
        xlsx_path = str(tmp_path / "orders_bridge.xlsx")
        wb.save(xlsx_path)

        df = _xlsx_to_spark_df(spark, xlsx_path)
        assert df.count() == 5
        assert "order_id" in df.columns
        assert "total_amount" in df.columns

    def test_amount_update_reflected_in_delta(self, _m, spark, cfg, log, tmp_path):
        delta = str(tmp_path / "delta_upd")
        q = str(tmp_path / "q_upd")
        run(spark, cfg, log, source_df=spark.createDataFrame(_SAMPLE_ROWS[:1], ORDERS_SCHEMA),
            delta_path=delta, quarantine_base_path=q)

        updated_row = Row(
            order_num=1, order_id=101, user_id=11,
            order_timestamp=datetime(2025, 4, 1, 8, 15),
            total_amount=999.99, date=date(2025, 4, 1),
        )
        run(spark, cfg, log,
            source_df=spark.createDataFrame([updated_row], ORDERS_SCHEMA),
            delta_path=delta, quarantine_base_path=q)

        df = read_delta_table(spark, delta)
        assert df.filter("order_id = 101").first()["total_amount"] == 999.99
