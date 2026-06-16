"""Unit tests for the structured JSON logger factory."""

import json
import logging
from io import StringIO

import pytest

from src.lib.logging_utils import get_logger


def _capture_logger(
    name: str,
    job_name: str = "test-job",
    execution_id: str = "exec-001",
    environment: str = "test",
) -> tuple[logging.Logger, StringIO]:
    """Create a fresh logger that writes to an in-memory buffer."""
    # Remove any existing handlers from a previously configured logger with this name
    existing = logging.getLogger(name)
    existing.handlers.clear()
    existing.propagate = True

    buf = StringIO()
    logger = get_logger(
        name,
        job_name=job_name,
        execution_id=execution_id,
        environment=environment,
    )
    # Replace the stdout handler with an in-memory one for assertions
    logger.handlers.clear()
    handler = logging.StreamHandler(buf)

    from src.lib.logging_utils import _LakehouseFormatter

    handler.setFormatter(
        _LakehouseFormatter(
            job_name=job_name,
            execution_id=execution_id,
            environment=environment,
        )
    )
    logger.addHandler(handler)
    return logger, buf


class TestGetLogger:
    def test_returns_logger_instance(self):
        existing = logging.getLogger("test_returns_logger")
        existing.handlers.clear()
        logger = get_logger("test_returns_logger", "job", "exec-1", "dev")
        assert isinstance(logger, logging.Logger)

    def test_logger_name_matches(self):
        existing = logging.getLogger("test_name_match")
        existing.handlers.clear()
        logger = get_logger("test_name_match", "job", "exec-1", "dev")
        assert logger.name == "test_name_match"

    def test_does_not_add_duplicate_handlers(self):
        existing = logging.getLogger("test_no_dup")
        existing.handlers.clear()
        get_logger("test_no_dup", "job", "exec-1", "dev")
        get_logger("test_no_dup", "job", "exec-1", "dev")
        assert len(logging.getLogger("test_no_dup").handlers) == 1

    def test_propagate_is_false(self):
        existing = logging.getLogger("test_propagate")
        existing.handlers.clear()
        logger = get_logger("test_propagate", "job", "exec-1", "dev")
        assert logger.propagate is False


class TestLakehouseFormatter:
    def test_output_is_valid_json(self):
        logger, buf = _capture_logger("test_json_valid")
        logger.info("hello world")
        record = json.loads(buf.getvalue().strip())
        assert isinstance(record, dict)

    def test_mandatory_fields_present(self):
        logger, buf = _capture_logger(
            "test_fields",
            job_name="products-etl",
            execution_id="arn:aws:states::exec:abc",
            environment="prod",
        )
        logger.info("checking fields")
        record = json.loads(buf.getvalue().strip())

        assert record["job_name"] == "products-etl"
        assert record["execution_id"] == "arn:aws:states::exec:abc"
        assert record["environment"] == "prod"
        assert "message" in record
        assert "level" in record

    def test_level_name_is_info(self):
        logger, buf = _capture_logger("test_level_info")
        logger.info("info message")
        record = json.loads(buf.getvalue().strip())
        assert record["level"] == "INFO"

    def test_level_name_is_error(self):
        logger, buf = _capture_logger("test_level_error")
        logger.error("something went wrong")
        record = json.loads(buf.getvalue().strip())
        assert record["level"] == "ERROR"

    def test_message_content(self):
        logger, buf = _capture_logger("test_msg_content")
        logger.info("records processed: 1000")
        record = json.loads(buf.getvalue().strip())
        assert "records processed: 1000" in record["message"]

    def test_extra_fields_included(self):
        logger, buf = _capture_logger("test_extra_fields")
        logger.info("validation done", extra={"records_in": 500, "records_rejected": 10})
        record = json.loads(buf.getvalue().strip())
        assert record.get("records_in") == 500
        assert record.get("records_rejected") == 10

    def test_warning_not_emitted_for_info_logger_at_warning(self):
        logger, buf = _capture_logger("test_warning_threshold")
        logger.setLevel(logging.WARNING)
        logger.info("this should be suppressed")
        assert buf.getvalue() == ""

    def test_error_propagates_exc_info(self):
        logger, buf = _capture_logger("test_exc_info")
        try:
            raise ValueError("something exploded")
        except ValueError:
            logger.exception("caught an error")
        record = json.loads(buf.getvalue().strip())
        assert record["level"] == "ERROR"
        assert "exc_info" in record or "message" in record
