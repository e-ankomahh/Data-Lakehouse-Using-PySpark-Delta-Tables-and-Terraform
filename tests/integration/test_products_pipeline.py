"""Integration tests for the products ETL pipeline — full stack, local filesystem paths."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.glue_jobs.products_job import run
from src.lib.config import config_from_glue_args
from src.lib.delta_utils import read_delta_table
from src.lib.logging_utils import get_logger

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
_VALID_ARGS = {
    "JOB_NAME": "integration-products-job",
    "RAW_BUCKET": "test-raw",
    "PROCESSED_BUCKET": "test-processed",
    "QUARANTINE_BUCKET": "test-quarantine",
    "ARCHIVE_BUCKET": "test-archive",
    "ENVIRONMENT": "test",
}


@pytest.fixture
def cfg():
    return config_from_glue_args(_VALID_ARGS)


@pytest.fixture
def log(cfg):
    return get_logger("products", cfg.job_name, "integration-exec-001", cfg.environment)


@patch("src.glue_jobs.products_job.emit_job_metrics")
class TestProductsPipelineIntegration:
    def test_valid_fixture_produces_correct_row_count(self, _m, spark, cfg, log, tmp_path):
        result = run(
            spark,
            cfg,
            log,
            source_path=str(_FIXTURES_DIR),
            delta_path=str(tmp_path / "delta"),
            quarantine_base_path=str(tmp_path / "quarantine"),
        )
        # products_sample.csv has 15 valid rows
        assert result["total"] == 15
        assert result["rejected"] == 0
        assert result["inserted"] == 15

    def test_delta_table_readable_after_run(self, _m, spark, cfg, log, tmp_path):
        delta = str(tmp_path / "delta_read")
        run(
            spark,
            cfg,
            log,
            source_path=str(_FIXTURES_DIR),
            delta_path=delta,
            quarantine_base_path=str(tmp_path / "q"),
        )
        df = read_delta_table(spark, delta)
        assert df.count() == 15
        assert "product_id" in df.columns
        assert "product_name" in df.columns

    def test_invalid_fixture_quarantines_bad_rows(self, _m, spark, cfg, log, tmp_path):
        # Use the directory with ONLY the invalid CSV — copy it to a temp source dir
        src_dir = tmp_path / "invalid_src"
        src_dir.mkdir()
        import shutil
        shutil.copy(_FIXTURES_DIR / "products_invalid.csv", src_dir / "products_invalid.csv")

        q_base = str(tmp_path / "quarantine_inv")
        result = run(
            spark,
            cfg,
            log,
            source_path=str(src_dir),
            delta_path=str(tmp_path / "delta_inv"),
            quarantine_base_path=q_base,
        )
        # products_invalid.csv: 1 duplicate, 1 null product_id → 2 rejected
        assert result["rejected"] >= 2
        assert os.path.exists(os.path.join(q_base, "table=products"))

    def test_two_runs_are_idempotent(self, _m, spark, cfg, log, tmp_path):
        delta = str(tmp_path / "delta_idem")
        q = str(tmp_path / "q_idem")
        run(spark, cfg, log, source_path=str(_FIXTURES_DIR), delta_path=delta, quarantine_base_path=q)
        result = run(spark, cfg, log, source_path=str(_FIXTURES_DIR), delta_path=delta, quarantine_base_path=q)
        # Second run: no new inserts — all rows matched by product_id
        assert result["inserted"] == 0
        df = read_delta_table(spark, delta)
        assert df.count() == 15

    def test_all_schema_columns_present_in_delta(self, _m, spark, cfg, log, tmp_path):
        delta = str(tmp_path / "delta_schema")
        run(spark, cfg, log, source_path=str(_FIXTURES_DIR), delta_path=delta, quarantine_base_path=str(tmp_path / "q_schema"))
        df = read_delta_table(spark, delta)
        expected_cols = {"product_id", "department_id", "department", "product_name"}
        assert expected_cols.issubset(set(df.columns))
