locals {
  all_bucket_arns = [
    var.s3_bucket_arns.raw,
    var.s3_bucket_arns.processed,
    var.s3_bucket_arns.archive,
    var.s3_bucket_arns.quarantine,
    var.s3_bucket_arns.artifacts,
    var.s3_bucket_arns.logs,
  ]

  all_bucket_object_arns = [for arn in local.all_bucket_arns : "${arn}/*"]

  all_kms_arns = [
    var.kms_key_arns.raw,
    var.kms_key_arns.processed,
    var.kms_key_arns.archive,
    var.kms_key_arns.glue,
  ]
}

# ── GitHub OIDC Provider ──────────────────────────────────────────────────────

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1", "1c58a3a8518e8759bf075b76b750d4f2df264fcd"]
}

# ── GlueExecutionRole ─────────────────────────────────────────────────────────

data "aws_iam_policy_document" "glue_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_execution" {
  name               = "lakehouse-${var.environment}-glue-execution"
  assume_role_policy = data.aws_iam_policy_document.glue_trust.json
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_inline" {
  statement {
    sid    = "S3BucketAccess"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket",
      "s3:ListBucketMultipartUploads",
    ]
    resources = local.all_bucket_arns
  }

  statement {
    sid    = "S3ObjectAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = local.all_bucket_object_arns
  }

  statement {
    sid    = "KMSAccess"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]
    resources = local.all_kms_arns
  }

  statement {
    sid    = "CloudWatchMetrics"
    effect = "Allow"
    actions = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["Lakehouse/Pipeline"]
    }
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/glue/*"]
  }

  statement {
    sid    = "GlueCatalog"
    effect = "Allow"
    actions = [
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetDatabase",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:GetPartition",
      "glue:CreatePartition",
      "glue:BatchCreatePartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${var.account_id}:catalog",
      "arn:aws:glue:${var.aws_region}:${var.account_id}:database/lakehouse_db",
      "arn:aws:glue:${var.aws_region}:${var.account_id}:table/lakehouse_db/*",
    ]
  }

  statement {
    sid    = "GlueBookmarks"
    effect = "Allow"
    actions = [
      "glue:GetJobBookmark",
      "glue:ResetJobBookmark",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "glue_inline" {
  name   = "lakehouse-glue-inline"
  role   = aws_iam_role.glue_execution.id
  policy = data.aws_iam_policy_document.glue_inline.json
}

# ── StepFunctionsRole ─────────────────────────────────────────────────────────

data "aws_iam_policy_document" "sfn_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_iam_role" "step_functions" {
  name               = "lakehouse-${var.environment}-step-functions"
  assume_role_policy = data.aws_iam_policy_document.sfn_trust.json
}

data "aws_iam_policy_document" "sfn_inline" {
  statement {
    sid    = "GlueJobs"
    effect = "Allow"
    actions = [
      "glue:StartJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:BatchStopJobRun",
    ]
    resources = ["arn:aws:glue:${var.aws_region}:${var.account_id}:job/lakehouse-${var.environment}-*"]
  }

  statement {
    sid    = "GlueCrawlers"
    effect = "Allow"
    actions = [
      "glue:StartCrawler",
      "glue:GetCrawler",
    ]
    resources = ["arn:aws:glue:${var.aws_region}:${var.account_id}:crawler/lakehouse-${var.environment}-*"]
  }

  statement {
    sid    = "LambdaInvoke"
    effect = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:${var.aws_region}:${var.account_id}:function:lakehouse-${var.environment}-*"]
  }

  statement {
    sid    = "SNSPublish"
    effect = "Allow"
    actions = ["sns:Publish"]
    resources = ["arn:aws:sns:${var.aws_region}:${var.account_id}:lakehouse-alerts-${var.environment}"]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sfn_inline" {
  name   = "lakehouse-sfn-inline"
  role   = aws_iam_role.step_functions.id
  policy = data.aws_iam_policy_document.sfn_inline.json
}

# ── EventBridgeRole ───────────────────────────────────────────────────────────

data "aws_iam_policy_document" "eventbridge_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eventbridge" {
  name               = "lakehouse-${var.environment}-eventbridge"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_trust.json
}

data "aws_iam_policy_document" "eventbridge_inline" {
  statement {
    sid    = "StartSFN"
    effect = "Allow"
    actions = ["states:StartExecution"]
    resources = ["arn:aws:states:${var.aws_region}:${var.account_id}:stateMachine:lakehouse-pipeline-${var.environment}"]
  }
}

resource "aws_iam_role_policy" "eventbridge_inline" {
  name   = "lakehouse-eventbridge-inline"
  role   = aws_iam_role.eventbridge.id
  policy = data.aws_iam_policy_document.eventbridge_inline.json
}

# ── LambdaRole ────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "lakehouse-${var.environment}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_inline" {
  statement {
    sid    = "S3Archive"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:DeleteObject",
    ]
    resources = ["${var.s3_bucket_arns.raw}/*"]
  }

  statement {
    sid    = "S3ArchiveWrite"
    effect = "Allow"
    actions = ["s3:PutObject"]
    resources = ["${var.s3_bucket_arns.archive}/*"]
  }

  statement {
    sid    = "SFNCallback"
    effect = "Allow"
    actions = [
      "states:SendTaskSuccess",
      "states:SendTaskFailure",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_inline" {
  name   = "lakehouse-lambda-inline"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_inline.json
}

# ── GitHubActionsRole (OIDC) ──────────────────────────────────────────────────

data "aws_iam_policy_document" "github_actions_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "lakehouse-${var.environment}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_trust.json
}

data "aws_iam_policy_document" "github_actions_inline" {
  statement {
    sid    = "UploadArtifacts"
    effect = "Allow"
    actions = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [
      var.s3_bucket_arns.artifacts,
      "${var.s3_bucket_arns.artifacts}/*",
    ]
  }

  statement {
    sid    = "UpdateGlueJobs"
    effect = "Allow"
    actions = ["glue:UpdateJob", "glue:GetJob"]
    resources = ["arn:aws:glue:${var.aws_region}:${var.account_id}:job/lakehouse-${var.environment}-*"]
  }

  statement {
    sid    = "TerraformState"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
      "s3:DeleteObject",
    ]
    resources = [
      "arn:aws:s3:::lakehouse-tfstate-${var.account_id}",
      "arn:aws:s3:::lakehouse-tfstate-${var.account_id}/*",
    ]
  }

  statement {
    sid    = "TerraformStateLock"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
    ]
    resources = ["arn:aws:dynamodb:${var.aws_region}:${var.account_id}:table/lakehouse-tfstate-lock"]
  }

  statement {
    sid    = "PassGlueRole"
    effect = "Allow"
    actions = ["iam:PassRole"]
    resources = [aws_iam_role.glue_execution.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "github_actions_inline" {
  name   = "lakehouse-github-actions-inline"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_inline.json
}
