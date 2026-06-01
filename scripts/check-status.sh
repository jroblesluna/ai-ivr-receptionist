#!/usr/bin/env bash
#
# check-status.sh — Check the status of the PickUp DEV deployment.
#
# Usage:
#   ./scripts/check-status.sh
#

set -euo pipefail

AWS_REGION="${AWS_REGION:-us-west-2}"
INSTANCE_ID="${INSTANCE_ID:-i-0ec6a04044483bc3e}"
DOMAIN="pickup.dev.iol.pe"
PUBLIC_IP="16.148.61.214"

echo "═══════════════════════════════════════════════════════════════"
echo "  PickUp AI — DEV Environment Status Check"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# --- EC2 Instance ---
echo "▸ EC2 Instance ($INSTANCE_ID)"
STATUS=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --region "$AWS_REGION" \
  --query 'Reservations[0].Instances[0].State.Name' \
  --output text 2>/dev/null || echo "unknown")
echo "  Status: $STATUS"
echo "  Public IP: $PUBLIC_IP"
echo ""

# --- RDS ---
echo "▸ RDS Database (pickup-dev)"
RDS_STATUS=$(aws rds describe-db-instances \
  --db-instance-identifier pickup-dev \
  --region "$AWS_REGION" \
  --query 'DBInstances[0].DBInstanceStatus' \
  --output text 2>/dev/null || echo "not found")
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier pickup-dev \
  --region "$AWS_REGION" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text 2>/dev/null || echo "n/a")
echo "  Status: $RDS_STATUS"
echo "  Endpoint: $RDS_ENDPOINT"
echo ""

# --- ECR ---
echo "▸ ECR Repository (pickup-dev)"
ECR_IMAGES=$(aws ecr describe-images \
  --repository-name pickup-dev \
  --region "$AWS_REGION" \
  --query 'length(imageDetails)' \
  --output text 2>/dev/null || echo "0")
echo "  Images: $ECR_IMAGES"
echo ""

# --- S3 Buckets ---
echo "▸ S3 Buckets"
for BUCKET in pickup-dev-reports pickup-dev-audio; do
  EXISTS=$(aws s3api head-bucket --bucket "$BUCKET" --region "$AWS_REGION" 2>&1 && echo "✓" || echo "✗")
  echo "  $BUCKET: $EXISTS"
done
echo ""

# --- Secrets Manager ---
echo "▸ Secrets Manager"
SECRET_STATUS=$(aws secretsmanager describe-secret \
  --secret-id pickup/dev/app-secrets \
  --region "$AWS_REGION" \
  --query 'Name' \
  --output text 2>/dev/null || echo "not found")
echo "  Secret: $SECRET_STATUS"
echo ""

# --- DNS Resolution ---
echo "▸ DNS ($DOMAIN)"
RESOLVED_IP=$(dig +short "$DOMAIN" 2>/dev/null || echo "unresolved")
if [ "$RESOLVED_IP" = "$PUBLIC_IP" ]; then
  echo "  Resolves to: $RESOLVED_IP ✓"
elif [ -z "$RESOLVED_IP" ]; then
  echo "  Resolves to: (not configured)"
  echo "  ⚠ Point $DOMAIN A record to $PUBLIC_IP"
else
  echo "  Resolves to: $RESOLVED_IP"
  echo "  ⚠ Expected: $PUBLIC_IP"
fi
echo ""

# --- Health Check ---
echo "▸ Health Check (http://$PUBLIC_IP:8000/health)"
HEALTH=$(curl -sf "http://$PUBLIC_IP:8000/health" 2>/dev/null || echo "unreachable")
if [ "$HEALTH" = "unreachable" ]; then
  echo "  Status: ✗ Not responding (app not deployed yet)"
else
  echo "  Status: ✓ $HEALTH"
fi
echo ""

# --- HTTPS Check ---
echo "▸ HTTPS (https://$DOMAIN/health)"
HTTPS_HEALTH=$(curl -sf "https://$DOMAIN/health" 2>/dev/null || echo "unreachable")
if [ "$HTTPS_HEALTH" = "unreachable" ]; then
  echo "  Status: ✗ Not responding (TLS not configured or DNS not pointed)"
else
  echo "  Status: ✓ $HTTPS_HEALTH"
fi
echo ""

echo "═══════════════════════════════════════════════════════════════"
echo "  Next Steps:"
echo "  1. Point DNS: $DOMAIN → $PUBLIC_IP (A record)"
echo "  2. Deploy app: push to main or run deploy workflow"
echo "  3. Fill secrets in AWS Secrets Manager"
echo "═══════════════════════════════════════════════════════════════"
