"""Shared pytest fixtures — session-scoped SparkSession with Delta Lake extensions."""

import pytest
from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def spark() -> SparkSession:
    """Return a local SparkSession configured for Delta Lake — shared across the test session."""
    session = (
        SparkSession.builder.master("local[2]")
        .appName("lakehouse-tests")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        # Avoid port conflicts when tests run in parallel
        .config("spark.ui.enabled", "false")
        # Speed up small-file operations in tests
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("WARN")
    yield session
    session.stop()
