"""Writes quarantined records to S3 as Parquet — write-once, no ACID required."""

import logging

from pyspark.sql import DataFrame

logger = logging.getLogger(__name__)


def write_to_quarantine(
    df: DataFrame,
    quarantine_base_path: str,
    table_name: str,
    execution_id: str,
    partition_date: str,
) -> int:
    """Append rejected records to a hive-partitioned quarantine path; return row count.

    Path pattern: <quarantine_base_path>/table=<name>/date=<date>/execution_id=<id>/
    Execution IDs containing colons (Step Functions ARNs) are sanitised for S3 path safety.
    """
    safe_exec_id = execution_id.replace(":", "_").replace("/", "_")
    path = (
        f"{quarantine_base_path}"
        f"/table={table_name}"
        f"/date={partition_date}"
        f"/execution_id={safe_exec_id}"
    )

    count = df.count()
    if count == 0:
        logger.info(
            "No quarantine records — skipping write",
            extra={"table": table_name, "path": path},
        )
        return 0

    df.write.mode("append").format("parquet").save(path)
    logger.info(
        "Quarantine write complete",
        extra={"path": path, "records_written": count, "table": table_name},
    )
    return count
