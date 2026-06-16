"""Unit tests for the products ETL job — uses local filesystem paths, no real AWS."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.glue_jobs.products_job import _build_rules, run
from src.lib.config import config_from_glue_args
from src.lib.exceptions import ValidationError
from src.lib.logging_utils import get_logger

_VALID_ARGS = {
    "JOB_NAME": "test-products-job",
    "RAW_BUCKET": "test-raw",
    "PROCESSED_BUCKET": "test-processed",
    "QUARANTINE_BUCKET": "test-quarantine",
    "ARCHIVE_BUCKET": "test-archive",
    "ENVIRONMENT": "test",
}

_CSV_HEADER = "product_id,department_id,department,product_name"


@pytest.fixture
def cfg():
    """Return a test LakehouseConfig built from valid args."""
    return config_from_glue_args(_VALID_ARGS)


@pytest.fixture
def log(cfg):
    """Return a structured logger for the test run."""
    return get_logger("products", cfg.job_name, "exec-test-001", cfg.environment)


def _write_csv(directory: Path, rows: list[str]) -> str:
    """Write a products CSV file to a tmp directory and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    content = _CSV_HEADER + "\n" + "\n".join(rows)
    (directory / "products.csv").write_text(content)
    return str(directory)


class TestBuildRules:
    def test_returns_four_rules(self):
        assert len(_build_rules()) == 4

    def test_first_rule_is_not_null_product_id(self):
        assert _build_rules()[0].rule_name == "not_null:product_id"

    def test_second_rule_is_unique_key_product_id(self):
        assert "unique_key" in _build_rules()[1].rule_name


@patch("src.glue_jobs.products_job.emit_job_metrics")
class TestProductsJobRun:
    def test_all_valid_data_inserted(self, _metrics, spark, cfg, log, tmp_path):
        src = _write_csv(tmp_path / "src1", ["1,4,produce,Bananas", "2,4,produce,Strawberries"])
        delta = str(tmp_path / "delta1")
        result = run(spark, cfg, log, source_path=src, delta_path=delta, quarantine_base_path=str(tmp_path / "q1"))
        assert result["total"] == 2
        assert result["valid"] == 2
        assert result["rejected"] == 0
        assert result["inserted"] == 2

    def test_null_product_id_quarantined(self, _metrics, spark, cfg, log, tmp_path):
        src = _write_csv(tmp_path / "src2", ["1,4,produce,Bananas", ",4,produce,No ID"])
        delta = str(tmp_path / "delta2")
        result = run(spark, cfg, log, source_path=src, delta_path=delta, quarantine_base_path=str(tmp_path / "q2"))
        assert result["rejected"] == 1
        assert result["valid"] == 1
        assert result["inserted"] == 1

    def test_duplicate_product_id_quarantined(self, _metrics, spark, cfg, log, tmp_path):
        src = _write_csv(
            tmp_path / "src3",
            ["1,4,produce,Bananas", "1,4,produce,Duplicate", "2,4,produce,Strawberries"],
        )
        delta = str(tmp_path / "delta3")
        result = run(spark, cfg, log, source_path=src, delta_path=delta, quarantine_base_path=str(tmp_path / "q3"))
        assert result["rejected"] == 1
        assert result["valid"] == 2

    def test_idempotent_rerun_produces_zero_inserts(self, _metrics, spark, cfg, log, tmp_path):
        src = _write_csv(tmp_path / "src4", ["1,4,produce,Bananas"])
        delta = str(tmp_path / "delta4")
        q = str(tmp_path / "q4")
        run(spark, cfg, log, source_path=src, delta_path=delta, quarantine_base_path=q)
        second = run(spark, cfg, log, source_path=src, delta_path=delta, quarantine_base_path=q)
        assert second["inserted"] == 0

    def test_update_changes_product_name(self, _metrics, spark, cfg, log, tmp_path):
        src_v1 = _write_csv(tmp_path / "src5a", ["1,4,produce,Bananas"])
        src_v2 = _write_csv(tmp_path / "src5b", ["1,4,produce,Organic Bananas"])
        delta = str(tmp_path / "delta5")
        q = str(tmp_path / "q5")
        run(spark, cfg, log, source_path=src_v1, delta_path=delta, quarantine_base_path=q)
        run(spark, cfg, log, source_path=src_v2, delta_path=delta, quarantine_base_path=q)
        from src.lib.delta_utils import read_delta_table
        df = read_delta_table(spark, delta)
        assert df.filter("product_id = 1").first()["product_name"] == "Organic Bananas"

    def test_exceeds_quarantine_threshold_raises_validation_error(self, _metrics, spark, log, tmp_path):
        strict_cfg = config_from_glue_args({**_VALID_ARGS, "MAX_QUARANTINE_RATIO": "0.01"})
        # 2 out of 3 rows are invalid → 66% failure ratio > 1% threshold
        src = _write_csv(tmp_path / "src6", ["1,4,produce,Bananas", ",4,produce,Null1", ",4,produce,Null2"])
        delta = str(tmp_path / "delta6")
        with pytest.raises(ValidationError):
            run(spark, strict_cfg, log, source_path=src, delta_path=delta, quarantine_base_path=str(tmp_path / "q6"))

    def test_empty_source_returns_all_zeros(self, _metrics, spark, cfg, log, tmp_path):
        src = tmp_path / "src7"
        src.mkdir()
        (src / "products.csv").write_text(_CSV_HEADER + "\n")
        result = run(spark, cfg, log, source_path=str(src), delta_path=str(tmp_path / "delta7"), quarantine_base_path=str(tmp_path / "q7"))
        assert result == {"total": 0, "valid": 0, "rejected": 0, "inserted": 0, "updated": 0}

    def test_metrics_emitted_on_success(self, mock_metrics, spark, cfg, log, tmp_path):
        src = _write_csv(tmp_path / "src8", ["1,4,produce,Bananas"])
        run(spark, cfg, log, source_path=src, delta_path=str(tmp_path / "delta8"), quarantine_base_path=str(tmp_path / "q8"))
        mock_metrics.assert_called_once()

    def test_quarantine_file_written_for_invalid_rows(self, _metrics, spark, cfg, log, tmp_path):
        src = _write_csv(tmp_path / "src9", ["1,4,produce,Bananas", ",4,produce,Null ID"])
        q_base = str(tmp_path / "q9")
        run(spark, cfg, log, source_path=src, delta_path=str(tmp_path / "delta9"), quarantine_base_path=q_base)
        import os
        assert os.path.exists(os.path.join(q_base, "table=products"))
