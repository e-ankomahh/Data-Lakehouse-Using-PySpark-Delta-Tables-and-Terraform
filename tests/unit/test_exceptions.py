"""Unit tests for the custom exception hierarchy."""

import pytest

from src.lib.exceptions import (
    BookmarkError,
    ConfigurationError,
    DeltaMergeError,
    DuplicateKeyError,
    GlueJobError,
    LakehouseException,
    NullKeyError,
    ReferentialIntegrityError,
    S3Error,
    S3ReadError,
    S3WriteError,
    SchemaError,
    ValidationError,
)


# ── Inheritance checks ────────────────────────────────────────────────────────


class TestExceptionHierarchy:
    def test_all_exceptions_are_lakehouse_exceptions(self):
        """Every custom exception must inherit from LakehouseException."""
        leaf_exceptions = [
            ConfigurationError,
            SchemaError,
            ValidationError,
            NullKeyError,
            DuplicateKeyError,
            ReferentialIntegrityError,
            S3Error,
            S3ReadError,
            S3WriteError,
            GlueJobError,
            BookmarkError,
            DeltaMergeError,
        ]
        for exc_class in leaf_exceptions:
            assert issubclass(exc_class, LakehouseException), (
                f"{exc_class.__name__} must inherit from LakehouseException"
            )

    def test_null_key_is_validation_error(self):
        assert issubclass(NullKeyError, ValidationError)

    def test_duplicate_key_is_validation_error(self):
        assert issubclass(DuplicateKeyError, ValidationError)

    def test_referential_integrity_is_validation_error(self):
        assert issubclass(ReferentialIntegrityError, ValidationError)

    def test_s3_read_is_s3_error(self):
        assert issubclass(S3ReadError, S3Error)

    def test_s3_write_is_s3_error(self):
        assert issubclass(S3WriteError, S3Error)

    def test_bookmark_is_glue_job_error(self):
        assert issubclass(BookmarkError, GlueJobError)

    def test_delta_merge_is_glue_job_error(self):
        assert issubclass(DeltaMergeError, GlueJobError)


# ── Raise and catch ───────────────────────────────────────────────────────────


class TestExceptionRaising:
    def test_validation_error_stores_failure_ratio(self):
        exc = ValidationError("too many bad records", failure_ratio=0.12)
        assert exc.failure_ratio == 0.12
        assert "too many bad records" in str(exc)

    def test_validation_error_default_ratio_is_zero(self):
        exc = ValidationError("error")
        assert exc.failure_ratio == 0.0

    def test_s3_error_stores_bucket_and_key(self):
        exc = S3ReadError("read failed", bucket="my-bucket", key="path/to/file.csv")
        assert exc.bucket == "my-bucket"
        assert exc.key == "path/to/file.csv"

    def test_s3_error_default_bucket_and_key_are_empty(self):
        exc = S3Error("generic s3 error")
        assert exc.bucket == ""
        assert exc.key == ""

    def test_catch_by_base_class(self):
        with pytest.raises(LakehouseException):
            raise NullKeyError("null pk detected", failure_ratio=0.05)

    def test_catch_specific_before_base(self):
        """More specific exception should be caught before the base class."""
        caught_specific = False
        try:
            raise DeltaMergeError("merge failed")
        except GlueJobError:
            caught_specific = True
        except LakehouseException:
            pass
        assert caught_specific

    def test_configuration_error_is_catchable_as_exception(self):
        with pytest.raises(Exception):
            raise ConfigurationError("missing env var")

    def test_schema_error_message(self):
        exc = SchemaError("column 'order_id' expected IntegerType, got StringType")
        assert "order_id" in str(exc)
