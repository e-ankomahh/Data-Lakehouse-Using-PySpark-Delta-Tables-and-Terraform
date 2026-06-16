#!/usr/bin/env bash
# Bootstrap the Terraform remote state backend (one-time manual step).
# Run this BEFORE the first `terraform init` in any environment.
#
# Usage: bash scripts/bootstrap_terraform_backend.sh <aws-account-id> [region]

set -euo pipefail

ACCOUNT_ID="${1:?Usage: $0 <aws-account-id> [region]}"
REGION="${2:-us-east-1}"

BUCKET_NAME="lakehouse-tfstate-${ACCOUNT_ID}"
TABLE_NAME="lakehouse-tfstate-lock"
KEY_ALIAS="alias/lakehouse-tfstate"

echo "==> Bootstrapping Terraform state backend"
echo "    Account : ${ACCOUNT_ID}"
echo "    Region  : ${REGION}"
echo "    Bucket  : ${BUCKET_NAME}"
echo "    DynamoDB: ${TABLE_NAME}"
echo ""

# 1. Create KMS key for state encryption
echo "--> Creating KMS key for Terraform state..."
KEY_ID=$(aws kms create-key \
  --description "Terraform state encryption key for lakehouse-ecommerce" \
  --region "${REGION}" \
  --query "KeyMetadata.KeyId" \
  --output text)

aws kms create-alias \
  --alias-name "${KEY_ALIAS}" \
  --target-key-id "${KEY_ID}" \
  --region "${REGION}"

aws kms enable-key-rotation \
  --key-id "${KEY_ID}" \
  --region "${REGION}"

echo "    KMS key created: ${KEY_ID}"

# 2. Create S3 bucket for state
echo "--> Creating S3 state bucket..."
if [ "${REGION}" = "us-east-1" ]; then
  aws s3api create-bucket \
    --bucket "${BUCKET_NAME}" \
    --region "${REGION}"
else
  aws s3api create-bucket \
    --bucket "${BUCKET_NAME}" \
    --region "${REGION}" \
    --create-bucket-configuration LocationConstraint="${REGION}"
fi

aws s3api put-bucket-versioning \
  --bucket "${BUCKET_NAME}" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "${BUCKET_NAME}" \
  --server-side-encryption-configuration "{
    \"Rules\": [{
      \"ApplyServerSideEncryptionByDefault\": {
        \"SSEAlgorithm\": \"aws:kms\",
        \"KMSMasterKeyID\": \"${KEY_ID}\"
      },
      \"BucketKeyEnabled\": true
    }]
  }"

aws s3api put-public-access-block \
  --bucket "${BUCKET_NAME}" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "    S3 bucket created and secured."

# 3. Create DynamoDB lock table
echo "--> Creating DynamoDB lock table..."
aws dynamodb create-table \
  --table-name "${TABLE_NAME}" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "${REGION}" \
  --output text > /dev/null

echo "    DynamoDB table created."

echo ""
echo "==> Bootstrap complete. Update infrastructure/backend.tf:"
echo "    bucket     = \"${BUCKET_NAME}\""
echo "    region     = \"${REGION}\""
echo "    kms_key_id = \"${KEY_ALIAS}\""
echo ""
echo "Then run: cd infrastructure/environments/dev && terraform init"
