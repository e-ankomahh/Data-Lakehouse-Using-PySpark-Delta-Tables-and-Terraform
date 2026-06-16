variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "account_id" {
  description = "AWS account ID — used to construct globally unique S3 bucket names."
  type        = string
}

variable "alert_email" {
  description = "Email address to receive SNS pipeline alerts."
  type        = string
}

variable "github_org" {
  description = "GitHub organisation or username that owns the repository."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name (without the org prefix)."
  type        = string
  default     = "lakehouse-ecommerce"
}

variable "glue_worker_count" {
  description = "Number of G.1X Glue workers per job."
  type        = number
  default     = 2
}

variable "glue_job_timeout_minutes" {
  description = "Maximum runtime in minutes for each Glue job."
  type        = number
  default     = 60
}
