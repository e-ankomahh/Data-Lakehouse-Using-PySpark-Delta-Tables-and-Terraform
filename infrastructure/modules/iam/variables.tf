variable "environment" { type = string }
variable "account_id"  { type = string }
variable "aws_region"  { type = string }
variable "github_org"  { type = string }
variable "github_repo" { type = string }

variable "s3_bucket_arns" {
  description = "ARNs of all lakehouse S3 buckets."
  type = object({
    raw        = string
    processed  = string
    archive    = string
    quarantine = string
    artifacts  = string
    logs       = string
  })
}

variable "kms_key_arns" {
  description = "ARNs of KMS keys used by Glue and S3."
  type = object({
    raw       = string
    processed = string
    archive   = string
    glue      = string
  })
}
