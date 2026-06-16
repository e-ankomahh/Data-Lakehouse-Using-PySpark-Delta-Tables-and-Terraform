# Root module — wires all sub-modules together.
# Each module is defined in infrastructure/modules/<name>/.

locals {
  name_prefix = "lakehouse-${var.environment}"
}

module "kms" {
  source      = "./modules/kms"
  environment = var.environment
  account_id  = var.account_id
}

module "s3" {
  source      = "./modules/s3"
  environment = var.environment
  account_id  = var.account_id

  kms_key_arns = {
    raw        = module.kms.raw_key_arn
    processed  = module.kms.processed_key_arn
    archive    = module.kms.archive_key_arn
    logs       = module.kms.logs_key_arn
    artifacts  = module.kms.artifacts_key_arn
  }

  depends_on = [module.kms]
}

module "iam" {
  source      = "./modules/iam"
  environment = var.environment
  account_id  = var.account_id
  aws_region  = var.aws_region
  github_org  = var.github_org
  github_repo = var.github_repo

  s3_bucket_arns = {
    raw         = module.s3.raw_bucket_arn
    processed   = module.s3.processed_bucket_arn
    archive     = module.s3.archive_bucket_arn
    quarantine  = module.s3.quarantine_bucket_arn
    artifacts   = module.s3.artifacts_bucket_arn
    logs        = module.s3.logs_bucket_arn
  }

  kms_key_arns = {
    raw       = module.kms.raw_key_arn
    processed = module.kms.processed_key_arn
    archive   = module.kms.archive_key_arn
    glue      = module.kms.glue_key_arn
  }

  depends_on = [module.s3, module.kms]
}

module "sns" {
  source      = "./modules/sns"
  environment = var.environment
  alert_email = var.alert_email
  kms_key_arn = module.kms.sns_key_arn

  depends_on = [module.kms]
}

module "monitoring" {
  source      = "./modules/monitoring"
  environment = var.environment
  kms_key_arn = module.kms.logs_key_arn

  sns_alert_topic_arn = module.sns.alert_topic_arn

  depends_on = [module.sns]
}

module "athena" {
  source              = "./modules/athena"
  environment         = var.environment
  logs_bucket_name    = module.s3.logs_bucket_name
  kms_key_arn         = module.kms.logs_key_arn

  depends_on = [module.s3, module.kms]
}

module "lambda" {
  source              = "./modules/lambda"
  environment         = var.environment
  lambda_role_arn     = module.iam.lambda_role_arn
  raw_bucket_name     = module.s3.raw_bucket_name
  archive_bucket_name = module.s3.archive_bucket_name

  depends_on = [module.iam, module.s3]
}

module "glue" {
  source      = "./modules/glue"
  environment = var.environment
  aws_region  = var.aws_region

  glue_role_arn      = module.iam.glue_execution_role_arn
  artifacts_bucket   = module.s3.artifacts_bucket_name
  raw_bucket         = module.s3.raw_bucket_name
  processed_bucket   = module.s3.processed_bucket_name
  quarantine_bucket  = module.s3.quarantine_bucket_name
  archive_bucket     = module.s3.archive_bucket_name
  logs_bucket        = module.s3.logs_bucket_name
  glue_kms_key_arn   = module.kms.glue_key_arn
  worker_count       = var.glue_worker_count
  job_timeout        = var.glue_job_timeout_minutes

  depends_on = [module.iam, module.s3, module.kms, module.monitoring]
}

module "step_functions" {
  source      = "./modules/step_functions"
  environment = var.environment
  aws_region  = var.aws_region
  account_id  = var.account_id

  sfn_role_arn           = module.iam.step_functions_role_arn
  products_job_name      = module.glue.products_job_name
  orders_job_name        = module.glue.orders_job_name
  order_items_job_name   = module.glue.order_items_job_name
  products_crawler_name  = module.glue.products_crawler_name
  orders_crawler_name    = module.glue.orders_crawler_name
  order_items_crawler_name = module.glue.order_items_crawler_name
  archive_lambda_arn     = module.lambda.archive_lambda_arn
  sns_alert_topic_arn    = module.sns.alert_topic_arn
  kms_key_arn            = module.kms.logs_key_arn

  depends_on = [module.glue, module.lambda, module.sns, module.iam]
}

module "eventbridge" {
  source      = "./modules/eventbridge"
  environment = var.environment

  raw_bucket_name        = module.s3.raw_bucket_name
  state_machine_arn      = module.step_functions.state_machine_arn
  eventbridge_role_arn   = module.iam.eventbridge_role_arn

  depends_on = [module.step_functions, module.s3, module.iam]
}
