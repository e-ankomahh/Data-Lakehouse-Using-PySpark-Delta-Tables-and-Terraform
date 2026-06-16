variable "environment"       { type = string }
variable "aws_region"        { type = string }
variable "glue_role_arn"     { type = string }
variable "artifacts_bucket"  { type = string }
variable "raw_bucket"        { type = string }
variable "processed_bucket"  { type = string }
variable "quarantine_bucket" { type = string }
variable "archive_bucket"    { type = string }
variable "logs_bucket"       { type = string }
variable "glue_kms_key_arn"  { type = string }
variable "worker_count"      { type = number; default = 2 }
variable "job_timeout"       { type = number; default = 60 }
