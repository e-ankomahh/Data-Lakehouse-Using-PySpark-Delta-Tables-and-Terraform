#!/usr/bin/env bash
# Upload the shared library wheel and all Glue job scripts to the S3 artifacts bucket.
# Run from the project root after configuring AWS credentials.
#
# Usage:
#   ./scripts/upload_glue_scripts.sh [dev|staging|prod] [<aws_account_id>]
#
# Examples:
#   ./scripts/upload_glue_scripts.sh dev 249946084242
#   AWS_ACCOUNT_ID=249946084242 ./scripts/upload_glue_scripts.sh staging

set -euo pipefail

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
ENV=${1:-dev}
ACCOUNT_ID=${2:-${AWS_ACCOUNT_ID:-""}}

if [[ -z "$ACCOUNT_ID" ]]; then
  echo "ERROR: AWS account ID is required."
  echo "       Pass as the second argument or set the AWS_ACCOUNT_ID environment variable."
  exit 1
fi

if [[ ! "$ENV" =~ ^(dev|staging|prod)$ ]]; then
  echo "ERROR: environment must be dev, staging, or prod (got '${ENV}')."
  exit 1
fi

# ---------------------------------------------------------------------------
# S3 paths
# ---------------------------------------------------------------------------
ARTIFACTS_BUCKET="lakehouse-artifacts-${ENV}-${ACCOUNT_ID}"
SCRIPTS_PREFIX="s3://${ARTIFACTS_BUCKET}/scripts"
LIBS_PREFIX="s3://${ARTIFACTS_BUCKET}/libs"
LAMBDA_PREFIX="s3://${ARTIFACTS_BUCKET}/lambda"

echo ""
echo "==> Environment : ${ENV}"
echo "==> Bucket      : ${ARTIFACTS_BUCKET}"
echo ""

# ---------------------------------------------------------------------------
# Build the wheel
# ---------------------------------------------------------------------------
echo "==> Building shared library wheel..."
pip install build==1.2.1 --quiet
python -m build --wheel --outdir dist/ --no-isolation 2>&1 | tail -5

WHEEL=$(ls dist/lakehouse_ecommerce-*.whl 2>/dev/null | sort -V | tail -1)
if [[ -z "$WHEEL" ]]; then
  echo "ERROR: No wheel found in dist/. Build may have failed."
  exit 1
fi
WHEEL_NAME=$(basename "$WHEEL")
echo "    Built: ${WHEEL_NAME}"

# ---------------------------------------------------------------------------
# Upload wheel
# ---------------------------------------------------------------------------
echo ""
echo "==> Uploading wheel → ${LIBS_PREFIX}/${WHEEL_NAME}"
aws s3 cp "$WHEEL" "${LIBS_PREFIX}/${WHEEL_NAME}"

# ---------------------------------------------------------------------------
# Upload Glue scripts
# ---------------------------------------------------------------------------
echo ""
echo "==> Uploading Glue scripts → ${SCRIPTS_PREFIX}/"
for script in \
  src/glue_jobs/products_job.py \
  src/glue_jobs/orders_job.py \
  src/glue_jobs/order_items_job.py
do
  dest="${SCRIPTS_PREFIX}/$(basename "$script")"
  aws s3 cp "$script" "$dest"
  echo "    $(basename "$script") → ${dest}"
done

# ---------------------------------------------------------------------------
# Upload archive Lambda
# ---------------------------------------------------------------------------
echo ""
echo "==> Uploading Lambda handler → ${LAMBDA_PREFIX}/archive_handler.py"
aws s3 cp src/lambda/archive_handler.py "${LAMBDA_PREFIX}/archive_handler.py"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "✓ Upload complete."
echo ""
echo "  Wheel  : ${LIBS_PREFIX}/${WHEEL_NAME}"
echo "  Scripts: ${SCRIPTS_PREFIX}/"
echo "  Lambda : ${LAMBDA_PREFIX}/archive_handler.py"
echo ""
echo "Next: run 'terraform apply' in infrastructure/environments/${ENV}/"
echo "      to point the Glue jobs at the new scripts and wheel."
echo ""

# ---------------------------------------------------------------------------
# Optional: update Glue job DefaultArguments to reference the new wheel.
# Uncomment the block below when upgrading the wheel version across environments.
# ---------------------------------------------------------------------------
# WHEEL_S3="${LIBS_PREFIX}/${WHEEL_NAME}"
# declare -A JOBS=(
#   [products]="products_job.py"
#   [orders]="orders_job.py"
#   [order-items]="order_items_job.py"
# )
# echo "==> Updating Glue job definitions..."
# for name in "${!JOBS[@]}"; do
#   JOB_NAME="lakehouse-${ENV}-${name}-etl"
#   aws glue update-job \
#     --job-name "$JOB_NAME" \
#     --job-update "{
#       \"DefaultArguments\": {\"--extra-py-files\": \"${WHEEL_S3}\"}
#     }"
#   echo "    Updated ${JOB_NAME}"
# done
