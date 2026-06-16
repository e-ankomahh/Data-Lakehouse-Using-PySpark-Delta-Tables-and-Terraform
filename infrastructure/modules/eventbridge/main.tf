resource "aws_cloudwatch_event_rule" "raw_file_arrival" {
  name        = "lakehouse-${var.environment}-raw-file-arrival"
  description = "Triggers the lakehouse pipeline when a file lands in the raw/incoming/ prefix."

  # S3 EventBridge integration must be enabled on the raw bucket (done in s3 module).
  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [var.raw_bucket_name] }
      object = { key = [{ prefix = "incoming/" }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "sfn_target" {
  rule     = aws_cloudwatch_event_rule.raw_file_arrival.name
  arn      = var.state_machine_arn
  role_arn = var.eventbridge_role_arn

  # Extract bucket and key from the S3 event and pass them as SFN input.
  input_transformer {
    input_paths = {
      bucket = "$.detail.bucket.name"
      key    = "$.detail.object.key"
    }
    input_template = jsonencode({
      trigger_bucket = "<bucket>"
      trigger_key    = "<key>"
    })
  }
}
