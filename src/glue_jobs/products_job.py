"""Products ETL job — reads CSV from raw S3, validates, quarantines, and upserts into Delta."""

import sys
import time
import traceback
from datetime import date

from pyspark.sql import SparkSession

from src.data_quality.quarantine import write_to_quarantine
from src.data_quality.rules import NotNullRule, UniqueKeyRule
from src.data_quality.validator import DataQualityValidator
from src.lib.config import LakehouseConfig, config_from_glue_args
from src.lib.delta_utils import create_delta_table_if_not_exists, write_delta_table_merge
from src.lib.exceptions import LakehouseException, ValidationError
from src.lib.glue_utils import commit_job, init_glue_job, resolve_args
from src.lib.logging_utils import get_logger
from src.lib.metrics import emit_job_metrics
from src.lib.schema_definitions import PARTITION_COLS, PRIMARY_KEYS, PRODUCTS_SCHEMA

TABLE = "products"
REQUIRED_ARGS = [
    "JOB_NAME",
    "RAW_BUCKET",
    "PROCESSED_BUCKET",
    "QUARANTINE_BUCKET",
    "ARCHIVE_BUCKET",
    "ENVIRONMENT",
]


def _build_rules() -> list:
    """Return the ordered list of validation rules for the products dataset."""
    return [
        NotNullRule("product_id"),
        UniqueKeyRule(["product_id"]),
        NotNullRule("department"),
        NotNullRule("product_name"),
    ]


def run(
    spark: SparkSession,
    cfg: LakehouseConfig,
    log,
    *,
    source_path: str | None = None,
    delta_path: str | None = None,
    quarantine_base_path: str | None = None,
) -> dict:
    """Execute the products ETL pipeline; returns a summary dict of counts.

    Keyword path overrides allow tests to inject local filesystem paths instead
    of s3:// URIs without changing production config.
    """
    start_ts = time.time()

    if source_path is None:
        source_path = f"s3://{cfg.s3.raw_bucket}/incoming/"
    if delta_path is None:
        delta_path = cfg.s3.products_delta_path
    if quarantine_base_path is None:
        quarantine_base_path = f"s3://{cfg.s3.quarantine_bucket}"

    log.info(
        "Products job started",
        extra={"table": TABLE, "source_path": source_path, "environment": cfg.environment},
    )

    # --- Read ---
    raw_df = (
        spark.read.option("header", "true")
        .option("mode", "PERMISSIVE")
        .schema(PRODUCTS_SCHEMA)
        .csv(source_path)
    )
    total_records = raw_df.count()
    log.info("Source CSV read complete", extra={"total_records": total_records, "table": TABLE})

    if total_records == 0:
        log.warning("No records in source — skipping processing", extra={"table": TABLE})
        return {"total": 0, "valid": 0, "rejected": 0, "inserted": 0, "updated": 0}

    # --- Validate ---
    validation_result = DataQualityValidator(_build_rules(), log).validate(raw_df)

    # --- Quarantine rejected rows ---
    if validation_result.records_failed > 0:
        write_to_quarantine(
            validation_result.invalid_df,
            quarantine_base_path,
            TABLE,
            cfg.execution_id,
            str(date.today()),
        )

    # --- Abort if failure ratio exceeds threshold ---
    if validation_result.failure_ratio > cfg.validation.max_quarantine_ratio:
        raise ValidationError(
            f"Quarantine ratio {validation_result.failure_ratio:.2%} exceeds threshold "
            f"{cfg.validation.max_quarantine_ratio:.2%} — bookmark will NOT be committed",
            failure_ratio=validation_result.failure_ratio,
        )

    # --- Ensure Delta table exists before first write ---
    create_delta_table_if_not_exists(
        spark, PRODUCTS_SCHEMA, delta_path, PARTITION_COLS[TABLE]
    )

    # --- Upsert into Delta ---
    merge_result = write_delta_table_merge(
        spark, validation_result.valid_df, delta_path, PRIMARY_KEYS[TABLE]
    )

    duration_ms = int((time.time() - start_ts) * 1000)

    emit_job_metrics(
        job_name=cfg.job_name,
        environment=cfg.environment,
        records_in=total_records,
        records_valid=validation_result.records_passed,
        records_rejected=validation_result.records_failed,
        rows_inserted=merge_result.rows_inserted,
        rows_updated=merge_result.rows_updated,
        duration_ms=duration_ms,
    )

    log.info(
        "Products job complete",
        extra={
            "event": "JOB_COMPLETE",
            "table": TABLE,
            "records_in": total_records,
            "records_valid": validation_result.records_passed,
            "records_rejected": validation_result.records_failed,
            "rows_inserted": merge_result.rows_inserted,
            "rows_updated": merge_result.rows_updated,
            "duration_ms": duration_ms,
        },
    )

    return {
        "total": total_records,
        "valid": validation_result.records_passed,
        "rejected": validation_result.records_failed,
        "inserted": merge_result.rows_inserted,
        "updated": merge_result.rows_updated,
    }


def main() -> None:
    """Glue entry point — resolves args, initialises Glue context, runs ETL, commits bookmark."""
    args = resolve_args(REQUIRED_ARGS)
    cfg = config_from_glue_args(args)
    log = get_logger(TABLE, cfg.job_name, cfg.execution_id, cfg.environment)

    _, glue_ctx, job = init_glue_job(cfg.job_name, args)
    spark = glue_ctx.spark_session if glue_ctx is not None else SparkSession.builder.getOrCreate()

    try:
        run(spark, cfg, log)
        commit_job(job)

    except ValidationError as exc:
        log.error(
            "Quarantine threshold exceeded — bookmark NOT committed",
            extra={"failure_ratio": exc.failure_ratio, "error": str(exc)},
        )
        sys.exit(1)

    except LakehouseException as exc:
        log.error(
            "Lakehouse error in products job",
            extra={"type": type(exc).__name__, "error": str(exc)},
        )
        sys.exit(1)

    except Exception as exc:
        log.error(
            "Unexpected failure in products job",
            extra={"error": str(exc), "traceback": traceback.format_exc()},
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
