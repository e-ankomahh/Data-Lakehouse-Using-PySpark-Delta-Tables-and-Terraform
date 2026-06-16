module "lakehouse" {
  source = "../../"

  environment              = "dev"
  aws_region               = var.aws_region
  account_id               = var.account_id
  alert_email              = var.alert_email
  github_org               = var.github_org
  github_repo              = var.github_repo
  glue_worker_count        = 2
  glue_job_timeout_minutes = 60
}
