"""Shared integration test fixtures — moto S3 environment for boto3 interactions."""

import os

import boto3
import pytest

try:
    from moto import mock_s3
    MOTO_AVAILABLE = True
except ImportError:
    MOTO_AVAILABLE = False


_BUCKETS = [
    "test-raw",
    "test-processed",
    "test-quarantine",
    "test-archive",
    "test-logs",
    "test-artifacts",
]


@pytest.fixture(scope="module", autouse=True)
def aws_env():
    """Inject fake AWS credentials so boto3 doesn't hit real AWS in integration tests."""
    old = {k: os.environ.get(k) for k in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                                            "AWS_DEFAULT_REGION"]}
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    yield
    for key, val in old.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


@pytest.fixture(scope="module")
def s3_mock():
    """Start a moto S3 mock for the duration of the test module."""
    if not MOTO_AVAILABLE:
        pytest.skip("moto not installed")
    with mock_s3():
        client = boto3.client("s3", region_name="us-east-1")
        for bucket in _BUCKETS:
            client.create_bucket(Bucket=bucket)
        yield client


@pytest.fixture
def test_cfg():
    """Return a LakehouseConfig pointing at the moto-mocked test buckets."""
    from src.lib.config import config_from_glue_args

    return config_from_glue_args(
        {
            "JOB_NAME": "integration-test-job",
            "RAW_BUCKET": "test-raw",
            "PROCESSED_BUCKET": "test-processed",
            "QUARANTINE_BUCKET": "test-quarantine",
            "ARCHIVE_BUCKET": "test-archive",
            "ENVIRONMENT": "test",
        }
    )
