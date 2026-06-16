# Package the archive Lambda from source — the Python file must exist at
# src/lambda/archive_handler.py before running terraform apply.
data "archive_file" "archive_handler" {
  type        = "zip"
  source_file = "${path.module}/../../../src/lambda/archive_handler.py"
  output_path = "${path.module}/.build/archive_handler.zip"
}

resource "aws_lambda_function" "archive_handler" {
  function_name = "lakehouse-${var.environment}-archive-handler"
  description   = "Moves a processed source file from raw/incoming/ to archive/ and signals Step Functions."

  role    = var.lambda_role_arn
  runtime = "python3.11"
  handler = "archive_handler.handler"
  timeout = 60

  filename         = data.archive_file.archive_handler.output_path
  source_code_hash = data.archive_file.archive_handler.output_base64sha256

  environment {
    variables = {
      ARCHIVE_BUCKET = var.archive_bucket_name
      ENVIRONMENT    = var.environment
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = { Name = "lakehouse-${var.environment}-archive-handler" }
}

resource "aws_cloudwatch_log_group" "archive_handler_logs" {
  name              = "/aws/lambda/lakehouse-${var.environment}-archive-handler"
  retention_in_days = 30
}
