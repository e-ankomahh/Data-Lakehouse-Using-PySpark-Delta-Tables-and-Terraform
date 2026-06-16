locals {
  jobs = {
    products    = "lakehouse-${var.environment}-products-etl"
    orders      = "lakehouse-${var.environment}-orders-etl"
    order_items = "lakehouse-${var.environment}-order-items-etl"
  }

  script_paths = {
    products    = "s3://${var.artifacts_bucket}/scripts/products_job.py"
    orders      = "s3://${var.artifacts_bucket}/scripts/orders_job.py"
    order_items = "s3://${var.artifacts_bucket}/scripts/order_items_job.py"
  }

  # Spark + Delta Lake configuration injected into every job
  spark_conf = join(" ", [
    "--conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension",
    "--conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog",
    "--conf spark.databricks.delta.retentionDurationCheck.enabled=false",
  ])

  common_args = {
    "--job-bookmark-option"              = "job-bookmark-enable"
    "--enable-metrics"                   = "true"
    "--enable-spark-ui"                  = "true"
    "--spark-event-logs-path"            = "s3://${var.logs_bucket}/spark-ui/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-continuous-log-filter"     = "true"
    "--datalake-formats"                 = "delta"
    "--conf"                             = local.spark_conf
    "--extra-py-files"                   = "s3://${var.artifacts_bucket}/libs/lakehouse_lib-1.0.0-py3-none-any.whl"
    "--RAW_BUCKET"                       = var.raw_bucket
    "--PROCESSED_BUCKET"                 = var.processed_bucket
    "--QUARANTINE_BUCKET"                = var.quarantine_bucket
    "--ARCHIVE_BUCKET"                   = var.archive_bucket
    "--ENVIRONMENT"                      = var.environment
    "--EXECUTION_ID"                     = ""
  }
}

# ── Glue Security Configuration ───────────────────────────────────────────────

resource "aws_glue_security_configuration" "lakehouse" {
  name = "lakehouse-${var.environment}-security-config"

  encryption_configuration {
    cloudwatch_encryption {
      cloudwatch_encryption_mode = "SSE-KMS"
      kms_key_arn                = var.glue_kms_key_arn
    }
    job_bookmarks_encryption {
      job_bookmarks_encryption_mode = "CSE-KMS"
      kms_key_arn                   = var.glue_kms_key_arn
    }
    s3_encryption {
      s3_encryption_mode = "SSE-KMS"
      kms_key_arn        = var.glue_kms_key_arn
    }
  }
}

# ── Glue Jobs (one per ETL dataset) ──────────────────────────────────────────

resource "aws_glue_job" "jobs" {
  for_each = local.jobs

  name              = each.value
  role_arn          = var.glue_role_arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = var.worker_count
  max_retries       = 1
  timeout           = var.job_timeout

  security_configuration = aws_glue_security_configuration.lakehouse.name

  command {
    name            = "glueetl"
    script_location = local.script_paths[each.key]
    python_version  = "3"
  }

  default_arguments = merge(local.common_args, {
    "--continuous-log-logGroup" = "/aws/glue/jobs/${each.value}"
  })

  execution_property {
    max_concurrent_runs = 1
  }

  tags = { Name = each.value }
}

# ── Glue Crawlers ─────────────────────────────────────────────────────────────

resource "aws_glue_crawler" "products" {
  name          = "lakehouse-${var.environment}-products-crawler"
  role          = var.glue_role_arn
  database_name = "lakehouse_db"
  description   = "Crawls the products Delta table and updates the Glue Data Catalog."

  delta_target {
    delta_tables   = ["s3://${var.processed_bucket}/delta/products/"]
    write_manifest = false
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }
}

resource "aws_glue_crawler" "orders" {
  name          = "lakehouse-${var.environment}-orders-crawler"
  role          = var.glue_role_arn
  database_name = "lakehouse_db"
  description   = "Crawls the orders Delta table and updates the Glue Data Catalog."

  delta_target {
    delta_tables   = ["s3://${var.processed_bucket}/delta/orders/"]
    write_manifest = false
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }
}

resource "aws_glue_crawler" "order_items" {
  name          = "lakehouse-${var.environment}-order-items-crawler"
  role          = var.glue_role_arn
  database_name = "lakehouse_db"
  description   = "Crawls the order_items Delta table and updates the Glue Data Catalog."

  delta_target {
    delta_tables   = ["s3://${var.processed_bucket}/delta/order_items/"]
    write_manifest = false
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }
}
