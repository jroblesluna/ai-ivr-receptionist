#!/usr/bin/env bash
#
# upload-secrets.sh — Upload secrets from .env to AWS Secrets Manager.
#
# Reads your local .env file and uploads the relevant keys to the
# Secrets Manager secret for the specified environment.
#
# Usage:
#   ./scripts/upload-secrets.sh          # defaults to dev
#   ./scripts/upload-secrets.sh prod     # for production
#
# Prerequisites:
#   - AWS CLI configured with appropriate permissions
#   - .env file in the project root with the secret values
#

set -euo pipefail

ENVIRONMENT="${1:-dev}"
AWS_REGION="${AWS_REGION:-us-west-2}"
SECRET_NAME="pickup/${ENVIRONMENT}/app-secrets"
ENV_FILE="${ENV_FILE:-.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Copy .env.example to .env and fill in your values."
  exit 1
fi

echo "═══════════════════════════════════════════════════════════════"
echo "  Uploading secrets to AWS Secrets Manager"
echo "  Environment: $ENVIRONMENT"
echo "  Secret: $SECRET_NAME"
echo "  Region: $AWS_REGION"
echo "  Source: $ENV_FILE"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Keys to extract from .env and upload to Secrets Manager
KEYS=(
  "TWILIO_ACCOUNT_SID"
  "TWILIO_AUTH_TOKEN"
  "TWILIO_API_KEY_SID"
  "TWILIO_API_KEY_SECRET"
  "TWILIO_TWIML_APP_SID"
  "TWILIO_VERIFY_SID"
  "OPENAI_API_KEY"
  "RESEND_API_KEY"
  "RESEND_FROM"
  "ELEVENLABS_API_KEY"
  "GOOGLE_TTS_API_KEY"
  "ADMIN_PASSWORD"
  "SECRET_KEY"
  "DATABASE_URL"
)

# Build JSON object from .env values
JSON="{"
FIRST=true

for KEY in "${KEYS[@]}"; do
  # Extract value from .env (handles quotes and spaces)
  VALUE=$(grep -E "^${KEY}=" "$ENV_FILE" 2>/dev/null | head -1 | sed "s/^${KEY}=//" | sed 's/^"//' | sed 's/"$//' || echo "")

  if [ -n "$VALUE" ] && [ "$VALUE" != "***" ] && [[ "$VALUE" != *"***"* ]]; then
    if [ "$FIRST" = true ]; then
      FIRST=false
    else
      JSON+=","
    fi
    # Escape special JSON characters in value
    ESCAPED_VALUE=$(echo "$VALUE" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip())[1:-1])")
    JSON+="\"${KEY}\":\"${ESCAPED_VALUE}\""
    echo "  ✓ $KEY"
  else
    echo "  ⚠ $KEY (empty or placeholder — skipped)"
  fi
done

JSON+="}"

# Also add DATABASE_URL if not already set (construct from RDS endpoint)
if ! echo "$JSON" | grep -q "DATABASE_URL" || echo "$JSON" | grep -q '"DATABASE_URL":""'; then
  RDS_ENDPOINT=$(aws rds describe-db-instances \
    --db-instance-identifier "pickup-${ENVIRONMENT}" \
    --region "$AWS_REGION" \
    --query 'DBInstances[0].Endpoint.Address' \
    --output text 2>/dev/null || echo "")

  if [ -n "$RDS_ENDPOINT" ]; then
    # Get the DB password from the current secret
    DB_PASSWORD=$(aws secretsmanager get-secret-value \
      --secret-id "$SECRET_NAME" \
      --region "$AWS_REGION" \
      --query 'SecretString' \
      --output text 2>/dev/null | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('DB_PASSWORD',''))" || echo "")

    if [ -n "$DB_PASSWORD" ]; then
      DB_URL="postgresql://pickup:${DB_PASSWORD}@${RDS_ENDPOINT}:5432/pickup"
      JSON=$(echo "$JSON" | python3 -c "
import sys, json
data = json.loads(sys.stdin.read())
data['DATABASE_URL'] = '$DB_URL'
print(json.dumps(data))
")
      echo "  ✓ DATABASE_URL (auto-constructed from RDS)"
    fi
  fi
fi

echo ""
echo "Uploading to Secrets Manager..."

# Update the secret value
aws secretsmanager put-secret-value \
  --secret-id "$SECRET_NAME" \
  --secret-string "$JSON" \
  --region "$AWS_REGION" \
  --output text --query 'Name'

echo ""
echo "✓ Secrets uploaded successfully to: $SECRET_NAME"
echo ""
echo "To verify:"
echo "  aws secretsmanager get-secret-value --secret-id $SECRET_NAME --region $AWS_REGION --query SecretString --output text | python3 -m json.tool"
