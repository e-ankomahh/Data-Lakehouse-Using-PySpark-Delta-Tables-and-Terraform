# Remote state stored in S3 with DynamoDB locking.
# The state bucket and DynamoDB table must be bootstrapped BEFORE running
# terraform init — see scripts/bootstrap_terraform_backend.sh.
terraform {
  backend "s3" {
    # Replace <account-id> with your actual AWS account ID.
    bucket         = "lakehouse-tfstate-<account-id>"
    key            = "lakehouse/${var.environment}/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "lakehouse-tfstate-lock"
    kms_key_id     = "alias/lakehouse-tfstate"
  }
}
