output "raw_bucket_name" {
  description = "S3 bucket name for raw incoming data."
  value       = module.s3.raw_bucket_name
}

output "processed_bucket_name" {
  description = "S3 bucket name for Delta Lake tables."
  value       = module.s3.processed_bucket_name
}

output "artifacts_bucket_name" {
  description = "S3 bucket name for Glue scripts and wheel library."
  value       = module.s3.artifacts_bucket_name
}

output "step_functions_arn" {
  description = "ARN of the lakehouse pipeline state machine."
  value       = module.step_functions.state_machine_arn
}

output "glue_execution_role_arn" {
  description = "ARN of the Glue execution IAM role."
  value       = module.iam.glue_execution_role_arn
}

output "sns_alert_topic_arn" {
  description = "ARN of the SNS topic for pipeline alerts."
  value       = module.sns.alert_topic_arn
}

output "github_actions_role_arn" {
  description = "ARN of the IAM role for GitHub Actions OIDC authentication."
  value       = module.iam.github_actions_role_arn
}
