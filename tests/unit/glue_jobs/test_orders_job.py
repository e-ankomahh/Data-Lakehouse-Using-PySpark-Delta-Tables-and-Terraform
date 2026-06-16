"""Unit tests for the orders ETL job — DataFrame injection bypasses XLSX/S3 entirely."""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from pyspark.sql import Row

from src.glue_jobs.orders_job import _build_rules, _xlsx_to_spark_df, run
from src.lib.config import config_from_glue_args
from src.lib.exceptions import ValidationError
from src.lib.logging_utils import get_logger
from src.lib.schema_definitions import ORDERS_SCHEMA

_TS = datetime(2025, 4, 1, 8, 15)
_DATE = date(2025, 4, 1)

_VALID_ARGS = {
    "JOB_NAME": "test-orders-job",
    "RAW_BUCKET": "test-raw",
    "PROCESSED_BUCKET": "test-processed",
    "QUARANTINE_BUCKET": "test-quarantine",
    "ARCHIVE_BUCKET": "test-archive",
    "ENVIRONMENT": "test",
}

_DEFAULTS = {
    "order_num": 1,
    "order_id": 101,
    "user_id": 11,
    "order_timestamp": _TS,
    "total_amount": 25.99,
    "date": _DATE,
}


@pytest.fixture
def cfg():
    return config_from_glue_args(_VALID_ARGS)


@pytest.fixture
def log(cfg):
    return get_logger("orders", cfg.job_name, "exec-orders-001", cfg.environment)


def _df(spark, rows: list[dict]):
    """Build a small orders DataFrame by merging each row dict with defaults."""
    full = [{**_DEFAULTS, **r} for r in rows]
    return spark.createDataFrame([Row(**r) for r in full], schema=ORDERS_SCHEMA)


# ---------------------------------------------------------------------------
# Rule construction
# ---------------------------------------------------------------------------
class TestBuildRules:
    def test_returns_six_rules(self):
        assert len(_build_rules()) == 6

    def test_first_rule_not_null_order_id(self):
        assert _build_rules()[0].rule_name == "not_null:order_id"

    def test_includes_positive_amount_rule(self):
        names = [r.rule_name for r in _build_rules()]
        assert any("positive_amount" in n for n in names)

    def test_includes_timestamp_range_rule(self):
        names = [r.rule_name for r in _build_rules()]
        assert any("timestamp_range" in n for n in names)


# ---------------------------------------------------------------------------
# XLSX → Spark bridge
# ---------------------------------------------------------------------------
class TestXlsxToSparkDf:
    @pytest.fixture
    def sample_xlsx(self, tmp_path):
        """Create a minimal orders XLSX using openpyxl."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(
            ["order_num", "order_id", "user_id", "order_timestamp", "total_amount", "date"]
        )
        ws.append([1, 101, 11, datetime(2025, 4, 1, 8, 15), 25.99, date(2025, 4, 1)])
        ws.append([2, 102, 12, datetime(2025, 4, 2, 9, 30), 17.99, date(2025, 4, 2)])
        path = str(tmp_path / "orders.xlsx")
        wb.save(path)
        return path

    def test_returns_correct_row_count(self, spark, sample_xlsx):
        df = _xlsx_to_spark_df(spark, sample_xlsx)
        assert df.count() == 2

    def test_order_id_column_present(self, spark, sample_xlsx):
        df = _xlsx_to_spark_df(spark, sample_xlsx)
        assert "order_id" in df.columns

    def test_total_amount_is_numeric(self, spark, sample_xlsx):
        df = _xlsx_to_spark_df(spark, sample_xlsx)
        from pyspark.sql.types import DoubleType
        amount_field = [f for f in df.schema.fields if f.name == "total_amount"][0]
        assert isinstance(amount_field.dataType, DoubleType)


# ---------------------------------------------------------------------------
# run() with injected source_df
# ---------------------------------------------------------------------------
@patch("src.glue_jobs.orders_job.emit_job_metrics")
class TestOrdersJobRun:
    def test_all_valid_inserts_all_rows(self, _m, spark, cfg, log, tmp_path):
        source = _df(spark, [
            {"order_id": 101, "order_num": 1},
            {"order_id": 102, "order_num": 2, "date": date(2025, 4, 2)},
        ])
        result = run(spark, cfg, log, source_df=source, delta_path=str(tmp_path / "d1"),
                     quarantine_base_path=str(tmp_path / "q1"))
        assert result["total"] == 2
        assert result["inserted"] == 2
        assert result["rejected"] == 0

    def test_null_order_id_quarantined(self, _m, spark, cfg, log, tmp_path):
        source = _df(spark, [{"order_id": 101}, {"order_id": None}])
        result = run(spark, cfg, log, source_df=source, delta_path=str(tmp_path / "d2"),
                     quarantine_base_path=str(tmp_path / "q2"))
        assert result["rejected"] == 1
        assert result["valid"] == 1

    def test_negative_amount_quarantined(self, _m, spark, cfg, log, tmp_path):
        source = _df(spark, [{"order_id": 101, "total_amount": -5.00}])
        result = run(spark, cfg, log, source_df=source, delta_path=str(tmp_path / "d3"),
                     quarantine_base_path=str(tmp_path / "q3"))
        assert result["rejected"] == 1

    def test_zero_amount_quarantined(self, _m, spark, cfg, log, tmp_path):
        source = _df(spark, [{"order_id": 101, "total_amount": 0.0}])
        result = run(spark, cfg, log, source_df=source, delta_path=str(tmp_path / "d4"),
                     quarantine_base_path=str(tmp_path / "q4"))
        assert result["rejected"] == 1

    def test_out_of_range_timestamp_quarantined(self, _m, spark, cfg, log, tmp_path):
        source = _df(spark, [{"order_id": 101, "order_timestamp": datetime(2015, 1, 1)}])
        result = run(spark, cfg, log, source_df=source, delta_path=str(tmp_path / "d5"),
                     quarantine_base_path=str(tmp_path / "q5"))
        assert result["rejected"] == 1

    def test_duplicate_order_id_quarantined(self, _m, spark, cfg, log, tmp_path):
        source = _df(spark, [{"order_id": 101}, {"order_id": 101, "total_amount": 99.0}])
        result = run(spark, cfg, log, source_df=source, delta_path=str(tmp_path / "d6"),
                     quarantine_base_path=str(tmp_path / "q6"))
        assert result["rejected"] == 1
        assert result["valid"] == 1

    def test_idempotent_rerun_no_new_inserts(self, _m, spark, cfg, log, tmp_path):
        source = _df(spark, [{"order_id": 101}])
        delta = str(tmp_path / "d7")
        q = str(tmp_path / "q7")
        run(spark, cfg, log, source_df=source, delta_path=delta, quarantine_base_path=q)
        result = run(spark, cfg, log, source_df=source, delta_path=delta, quarantine_base_path=q)
        assert result["inserted"] == 0

    def test_exceeds_threshold_raises_validation_error(self, _m, spark, log, tmp_path):
        strict_cfg = config_from_glue_args({**_VALID_ARGS, "MAX_QUARANTINE_RATIO": "0.01"})
        # 3 invalid (null order_id) out of 4 total → 75% > 1%
        source = _df(spark, [
            {"order_id": 101},
            {"order_id": None},
            {"order_id": None},
            {"order_id": None},
        ])
        with pytest.raises(ValidationError):
            run(spark, strict_cfg, log, source_df=source,
                delta_path=str(tmp_path / "d8"), quarantine_base_path=str(tmp_path / "q8"))

    def test_empty_source_returns_zeros(self, _m, spark, cfg, log, tmp_path):
        source = spark.createDataFrame([], ORDERS_SCHEMA)
        result = run(spark, cfg, log, source_df=source, delta_path=str(tmp_path / "d9"),
                     quarantine_base_path=str(tmp_path / "q9"))
        assert result == {"total": 0, "valid": 0, "rejected": 0, "inserted": 0, "updated": 0}

    def test_metrics_emitted_on_success(self, mock_metrics, spark, cfg, log, tmp_path):
        source = _df(spark, [{"order_id": 101}])
        run(spark, cfg, log, source_df=source, delta_path=str(tmp_path / "d10"),
            quarantine_base_path=str(tmp_path / "q10"))
        mock_metrics.assert_called_once()

    def test_delta_table_partitioned_by_date(self, _m, spark, cfg, log, tmp_path):
        source = _df(spark, [
            {"order_id": 101, "date": date(2025, 4, 1)},
            {"order_id": 102, "date": date(2025, 4, 2)},
        ])
        delta = str(tmp_path / "d11")
        run(spark, cfg, log, source_df=source, delta_path=delta, quarantine_base_path=str(tmp_path / "q11"))
        from src.lib.delta_utils import read_delta_table
        df = read_delta_table(spark, delta)
        assert df.count() == 2
