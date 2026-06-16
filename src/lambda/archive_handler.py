"""Lambda function that archives a processed source file and signals Step Functions."""

import json
import logging
import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
sfn = boto3.client("stepfunctions")

ARCHIVE_BUCKET = os.environ["ARCHIVE_BUCKET"]
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")


def handler(event: dict, context) -> dict:
    """Move the trigger file from raw/incoming/ to archive/ then signal Step Functions."""
    logger.info("Archive handler invoked", extra={"event": json.dumps(event)})

    trigger_bucket = event["trigger_bucket"]
    trigger_key = unquote_plus(event["trigger_key"])
    task_token = event["task_token"]

    try:
        archive_key = _build_archive_key(trigger_key)

        _copy_to_archive(trigger_bucket, trigger_key, archive_key)
        _delete_source(trigger_bucket, trigger_key)

        logger.info(
            "File archived successfully",
            extra={
                "source": f"s3://{trigger_bucket}/{trigger_key}",
                "destination": f"s3://{ARCHIVE_BUCKET}/{archive_key}",
            },
        )

        sfn.send_task_success(
            taskToken=task_token,
            output=json.dumps({"archived_key": archive_key}),
        )
        return {"status": "archived", "archive_key": archive_key}

    except Exception as exc:
        logger.exception("Archive failed", extra={"error": str(exc)})
        sfn.send_task_failure(
            taskToken=task_token,
            error="ArchiveError",
            cause=str(exc)[:256],
        )
        raise


def _build_archive_key(source_key: str) -> str:
    """Derive the archive destination key by prepending a date partition."""
    now = datetime.now(tz=timezone.utc)
    filename = source_key.split("/")[-1]
    return f"YYYY={now.year}/MM={now.month:02d}/DD={now.day:02d}/{filename}"


def _copy_to_archive(source_bucket: str, source_key: str, archive_key: str) -> None:
    """Copy an S3 object to the archive bucket."""
    s3.copy_object(
        CopySource={"Bucket": source_bucket, "Key": source_key},
        Bucket=ARCHIVE_BUCKET,
        Key=archive_key,
    )


def _delete_source(bucket: str, key: str) -> None:
    """Delete an S3 object from the source bucket."""
    s3.delete_object(Bucket=bucket, Key=key)
