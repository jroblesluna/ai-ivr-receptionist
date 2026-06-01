#!/usr/bin/env bash
# Bootstrap script: creates the S3 bucket and DynamoDB table for Terraform remote state.
# Run this ONCE before the first `terraform init`.

set -euo pipefail

AWS_REGION="${AWS_REGION:-us-west-2}"
STATE_BUCKET="pickup-ai-tf-state-040982"
LOCK_TABLE="pickup-ai-terraform-locks"

echo "Creating S3 bucket for Terraform state..."
if [ "$AWS_REGION" = "us-east-1" ]; then
  aws s3api create-bucket \
    --bucket "$STATE_BUCKET" \
    --region "$AWS_REGION" 2>/dev/null || true
else
  aws s3api create-bucket \
    --bucket "$STATE_BUCKET" \
    --region "$AWS_REGION" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION" 2>/dev/null || true
fi

aws s3api put-bucket-versioning \
  --bucket "$STATE_BUCKET" \
  --versioning-configuration Status=Enabled

aws s3api put-public-access-block \
  --bucket "$STATE_BUCKET" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "Creating DynamoDB table for state locking..."
aws dynamodb create-table \
  --table-name "$LOCK_TABLE" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$AWS_REGION" 2>/dev/null || true

echo "Bootstrap complete. You can now run: terraform init"
