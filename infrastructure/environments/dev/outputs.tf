output "github_actions_role_arn" {
  description = "ARN of the IAM role for GitHub Actions OIDC authentication."
  value       = module.lakehouse.github_actions_role_arn
}

output "raw_bucket_name" {
  description = "S3 bucket name for raw incoming data."
  value       = module.lakehouse.raw_bucket_name
}

output "processed_bucket_name" {
  description = "S3 bucket name for Delta Lake tables."
  value       = module.lakehouse.processed_bucket_name
}

output "artifacts_bucket_name" {
  description = "S3 bucket name for Glue scripts and wheel library."
  value       = module.lakehouse.artifacts_bucket_name
}

output "step_functions_arn" {
  description = "ARN of the lakehouse pipeline state machine."
  value       = module.lakehouse.step_functions_arn
}
