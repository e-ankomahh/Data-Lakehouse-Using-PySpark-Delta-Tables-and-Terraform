"""Unit tests for the LakehouseConfig factory."""

import pytest

from src.lib.config import LakehouseConfig, S3Config, config_from_glue_args
from src.lib.exceptions import ConfigurationError

_VALID_ARGS = {
    "JOB_NAME": "lakehouse-dev-products-etl",
    "EXECUTION_ID": "arn:aws:states::exec:abc123",
    "RAW_BUCKET": "lakehouse-raw-dev-123456",
    "PROCESSED_BUCKET": "lakehouse-processed-dev-123456",
    "QUARANTINE_BUCKET": "lakehouse-quarantine-dev-123456",
    "ARCHIVE_BUCKET": "lakehouse-archive-dev-123456",
    "ENVIRONMENT": "dev",
}


class TestConfigFromGlueArgs:
    def test_returns_lakehouse_config(self):
        cfg = config_from_glue_args(_VALID_ARGS)
        assert isinstance(cfg, LakehouseConfig)

    def test_environment_set_correctly(self):
        cfg = config_from_glue_args(_VALID_ARGS)
        assert cfg.environment == "dev"

    def test_job_name_set_correctly(self):
        cfg = config_from_glue_args(_VALID_ARGS)
        assert cfg.job_name == "lakehouse-dev-products-etl"

    def test_execution_id_set_correctly(self):
        cfg = config_from_glue_args(_VALID_ARGS)
        assert cfg.execution_id == "arn:aws:states::exec:abc123"

    def test_execution_id_defaults_to_local_when_absent(self):
        args = {k: v for k, v in _VALID_ARGS.items() if k != "EXECUTION_ID"}
        cfg = config_from_glue_args(args)
        assert cfg.execution_id == "local"

    def test_s3_prefixes_stripped(self):
        args = {**_VALID_ARGS, "RAW_BUCKET": "s3://lakehouse-raw-dev-123456/"}
        cfg = config_from_glue_args(args)
        assert cfg.s3.raw_bucket == "lakehouse-raw-dev-123456"

    def test_raises_on_missing_required_arg(self):
        for key in ("RAW_BUCKET", "PROCESSED_BUCKET", "QUARANTINE_BUCKET",
                    "ARCHIVE_BUCKET", "ENVIRONMENT", "JOB_NAME"):
            args = {k: v for k, v in _VALID_ARGS.items() if k != key}
            with pytest.raises(ConfigurationError, match=key):
                config_from_glue_args(args)

    def test_raises_on_blank_required_arg(self):
        args = {**_VALID_ARGS, "ENVIRONMENT": "   "}
        with pytest.raises(ConfigurationError):
            config_from_glue_args(args)

    def test_custom_quarantine_ratio(self):
        args = {**_VALID_ARGS, "MAX_QUARANTINE_RATIO": "0.10"}
        cfg = config_from_glue_args(args)
        assert cfg.validation.max_quarantine_ratio == pytest.approx(0.10)

    def test_invalid_quarantine_ratio_raises(self):
        args = {**_VALID_ARGS, "MAX_QUARANTINE_RATIO": "1.5"}
        with pytest.raises(ConfigurationError, match="MAX_QUARANTINE_RATIO"):
            config_from_glue_args(args)

    def test_glue_database_default(self):
        cfg = config_from_glue_args(_VALID_ARGS)
        assert cfg.glue.database == "lakehouse_db"


class TestS3Config:
    def _make(self) -> S3Config:
        return S3Config(
            raw_bucket="raw",
            processed_bucket="processed",
            quarantine_bucket="quarantine",
            archive_bucket="archive",
        )

    def test_products_delta_path(self):
        assert self._make().products_delta_path == "s3://processed/delta/products/"

    def test_orders_delta_path(self):
        assert self._make().orders_delta_path == "s3://processed/delta/orders/"

    def test_order_items_delta_path(self):
        assert self._make().order_items_delta_path == "s3://processed/delta/order_items/"

    def test_quarantine_base_path(self):
        assert self._make().quarantine_base_path == "s3://quarantine"

    def test_is_frozen(self):
        cfg = self._make()
        with pytest.raises((AttributeError, TypeError)):
            cfg.raw_bucket = "changed"  # type: ignore[misc]
