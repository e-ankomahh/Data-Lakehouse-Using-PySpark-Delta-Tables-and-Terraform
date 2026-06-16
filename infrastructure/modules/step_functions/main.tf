locals {
  # Build the ASL definition as a Terraform object so variable substitution
  # is handled natively — no external JSON template files needed.
  state_machine_definition = jsonencode({
    Comment = "Lakehouse ETL Pipeline — triggered by S3 file arrival in raw/incoming/"
    StartAt = "RunProductsAndOrdersInParallel"
    States = {

      # Products runs independently; Orders→OrderItems run sequentially — both
      # branches execute concurrently inside this Parallel state.
      RunProductsAndOrdersInParallel = {
        Type    = "Parallel"
        Comment = "Products and Orders+OrderItems processed concurrently."
        Branches = [
          {
            StartAt = "RunProductsJob"
            States = {
              RunProductsJob = {
                Type     = "Task"
                Resource = "arn:aws:states:::glue:startJobRun.sync:2"
                Parameters = {
                  JobName = var.products_job_name
                  Arguments = {
                    "--EXECUTION_ID.$" = "$$.Execution.Id"
                    "--TRIGGER_KEY.$"  = "$.trigger_key"
                    "--TRIGGER_BUCKET.$" = "$.trigger_bucket"
                  }
                }
                TimeoutSeconds = 1800
                Retry = [
                  {
                    ErrorEquals  = ["Glue.ConcurrentRunsExceededException"]
                    IntervalSeconds = 60
                    MaxAttempts  = 3
                    BackoffRate  = 2.0
                  },
                  {
                    ErrorEquals  = ["States.TaskFailed"]
                    IntervalSeconds = 30
                    MaxAttempts  = 2
                    BackoffRate  = 1.5
                  }
                ]
                Catch = [
                  {
                    ErrorEquals = ["States.ALL"]
                    Next        = "ProductsJobFailed"
                    ResultPath  = "$.error"
                  }
                ]
                End = true
              }
              ProductsJobFailed = {
                Type  = "Fail"
                Error = "ProductsJobError"
                Cause = "Products Glue job failed — check /aws/glue/jobs/ logs."
              }
            }
          },
          {
            StartAt = "RunOrdersJob"
            States = {
              RunOrdersJob = {
                Type     = "Task"
                Resource = "arn:aws:states:::glue:startJobRun.sync:2"
                Parameters = {
                  JobName = var.orders_job_name
                  Arguments = {
                    "--EXECUTION_ID.$" = "$$.Execution.Id"
                  }
                }
                TimeoutSeconds = 1800
                Retry = [
                  {
                    ErrorEquals  = ["Glue.ConcurrentRunsExceededException"]
                    IntervalSeconds = 60
                    MaxAttempts  = 3
                    BackoffRate  = 2.0
                  }
                ]
                Catch = [
                  {
                    ErrorEquals = ["States.ALL"]
                    Next        = "OrdersJobFailed"
                    ResultPath  = "$.error"
                  }
                ]
                Next = "RunOrderItemsJob"
              }
              RunOrderItemsJob = {
                Type     = "Task"
                Resource = "arn:aws:states:::glue:startJobRun.sync:2"
                Parameters = {
                  JobName = var.order_items_job_name
                  Arguments = {
                    "--EXECUTION_ID.$" = "$$.Execution.Id"
                  }
                }
                TimeoutSeconds = 3600
                Retry = [
                  {
                    ErrorEquals  = ["Glue.ConcurrentRunsExceededException"]
                    IntervalSeconds = 60
                    MaxAttempts  = 3
                    BackoffRate  = 2.0
                  }
                ]
                Catch = [
                  {
                    ErrorEquals = ["States.ALL"]
                    Next        = "OrderItemsJobFailed"
                    ResultPath  = "$.error"
                  }
                ]
                End = true
              }
              OrdersJobFailed = {
                Type  = "Fail"
                Error = "OrdersJobError"
                Cause = "Orders Glue job failed."
              }
              OrderItemsJobFailed = {
                Type  = "Fail"
                Error = "OrderItemsJobError"
                Cause = "Order items Glue job failed."
              }
            }
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "HandlePipelineFailure"
            ResultPath  = "$.error"
          }
        ]
        Next = "RunProductsCrawler"
      }

      RunProductsCrawler = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startCrawler.sync:2"
        Parameters = { Name = var.products_crawler_name }
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "HandlePipelineFailure"
            ResultPath  = "$.error"
          }
        ]
        Next = "RunOrdersCrawler"
      }

      RunOrdersCrawler = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startCrawler.sync:2"
        Parameters = { Name = var.orders_crawler_name }
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "HandlePipelineFailure"
            ResultPath  = "$.error"
          }
        ]
        Next = "RunOrderItemsCrawler"
      }

      RunOrderItemsCrawler = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startCrawler.sync:2"
        Parameters = { Name = var.order_items_crawler_name }
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "HandlePipelineFailure"
            ResultPath  = "$.error"
          }
        ]
        Next = "ArchiveSourceFiles"
      }

      ArchiveSourceFiles = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke.waitForTaskToken"
        Comment  = "Lambda moves the trigger file from raw/incoming/ to archive/. Uses waitForTaskToken so it can signal success asynchronously."
        Parameters = {
          FunctionName = var.archive_lambda_arn
          Payload = {
            "trigger_bucket.$" = "$.trigger_bucket"
            "trigger_key.$"    = "$.trigger_key"
            "task_token.$"     = "$$.Task.Token"
          }
        }
        TimeoutSeconds = 300
        Retry = [
          {
            ErrorEquals  = ["Lambda.ServiceException", "Lambda.AWSLambdaException"]
            IntervalSeconds = 10
            MaxAttempts  = 2
            BackoffRate  = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "HandlePipelineFailure"
            ResultPath  = "$.error"
          }
        ]
        Next = "NotifySuccess"
      }

      NotifySuccess = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn = var.sns_alert_topic_arn
          Subject  = "Lakehouse Pipeline SUCCESS"
          Message = {
            "Input.$" = "States.Format('Pipeline succeeded. Execution: {}', $$.Execution.Id)"
          }
        }
        End = true
      }

      HandlePipelineFailure = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn = var.sns_alert_topic_arn
          Subject  = "Lakehouse Pipeline FAILURE"
          Message = {
            "Input.$" = "States.Format('Pipeline FAILED. Execution: {}. Error: {}', $$.Execution.Id, $.error)"
          }
        }
        Next = "PipelineFailed"
      }

      PipelineFailed = {
        Type  = "Fail"
        Error = "PipelineError"
        Cause = "One or more pipeline stages failed — check SNS notification for details."
      }
    }
  })
}

resource "aws_cloudwatch_log_group" "sfn_logs" {
  name              = "/aws/states/lakehouse-pipeline-${var.environment}"
  retention_in_days = 30
  kms_key_id        = var.kms_key_arn
}

resource "aws_sfn_state_machine" "lakehouse_pipeline" {
  name     = "lakehouse-pipeline-${var.environment}"
  role_arn = var.sfn_role_arn
  type     = "STANDARD"

  definition = local.state_machine_definition

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_logs.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = { Name = "lakehouse-pipeline-${var.environment}" }
}
