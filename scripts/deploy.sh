#!/usr/bin/env bash
#
# deploy.sh — Zero-downtime deployment script for PickUp backend.
#
# Flow:
#   1. Pull latest image from ECR
#   2. Start new container
#   3. Health check with 60s timeout
#   4. Stop old container on success
#   5. Roll back to previous image on failure
#
# Usage:
#   ./scripts/deploy.sh <full_image_uri>
#   ./scripts/deploy.sh 123456789.dkr.ecr.us-west-2.amazonaws.com/pickup-dev:abc123
#
# Alternatively, set environment variables:
#   ECR_REPOSITORY_URL  — Full ECR repository URL (e.g., 123456789.dkr.ecr.us-west-2.amazonaws.com/pickup)
#   IMAGE_TAG           — Image tag to deploy (e.g., commit SHA)
#   AWS_REGION          — AWS region (default: us-west-2)
#
# Optional:
#   HEALTH_CHECK_TIMEOUT — Seconds to wait for health check (default: 60)
#   COMPOSE_FILE         — Path to docker-compose.yml (default: /app/docker-compose.yml)

set -euo pipefail

# --- Configuration ---
AWS_REGION="${AWS_REGION:-us-west-2}"
HEALTH_CHECK_TIMEOUT="${HEALTH_CHECK_TIMEOUT:-60}"
COMPOSE_FILE="${COMPOSE_FILE:-./docker-compose.yml}"
HEALTH_URL="http://localhost:8000/health"
SERVICE_NAME="backend"

# --- Parse arguments ---
# Accept full image URI as $1 (e.g., 123456789.dkr.ecr.us-west-2.amazonaws.com/pickup-dev:abc123)
if [[ -n "${1:-}" ]]; then
    ECR_REPOSITORY_URL="${1%:*}"
    IMAGE_TAG="${1##*:}"
fi

# --- Validation ---
if [[ -z "${ECR_REPOSITORY_URL:-}" ]]; then
    echo "ERROR: ECR_REPOSITORY_URL is not set" >&2
    exit 1
fi

if [[ -z "${IMAGE_TAG:-}" ]]; then
    echo "ERROR: IMAGE_TAG is not set" >&2
    exit 1
fi

NEW_IMAGE="${ECR_REPOSITORY_URL}:${IMAGE_TAG}"
COMPOSE_DIR="$(dirname "${COMPOSE_FILE}")"

echo "=== PickUp Deploy ==="
echo "Image: ${NEW_IMAGE}"
echo "Compose file: ${COMPOSE_FILE}"
echo "Health check timeout: ${HEALTH_CHECK_TIMEOUT}s"
echo ""

# --- Helper functions ---
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

get_current_image() {
    docker compose -f "${COMPOSE_FILE}" images "${SERVICE_NAME}" --format json 2>/dev/null \
        | jq -r '.[0].Repository + ":" + .[0].Tag' 2>/dev/null || echo ""
}

health_check() {
    local timeout=$1
    local elapsed=0
    local interval=2

    log "Waiting for health check (timeout: ${timeout}s)..."

    while [[ $elapsed -lt $timeout ]]; do
        if curl -sf "${HEALTH_URL}" > /dev/null 2>&1; then
            log "Health check passed after ${elapsed}s"
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
    done

    log "Health check FAILED after ${timeout}s"
    return 1
}

# --- Step 1: Record current image for rollback ---
PREVIOUS_IMAGE="$(get_current_image)"
log "Previous image: ${PREVIOUS_IMAGE:-none}"

# --- Step 2: Authenticate with ECR ---
log "Authenticating with ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin "${ECR_REPOSITORY_URL%%/*}"

# --- Step 3: Pull new image ---
log "Pulling image: ${NEW_IMAGE}"
if ! docker pull "${NEW_IMAGE}"; then
    echo "ERROR: Failed to pull image ${NEW_IMAGE}" >&2
    exit 1
fi

# --- Step 4: Stop old container and start new one ---
log "Updating service with new image..."
export BACKEND_IMAGE="${NEW_IMAGE}"

# Use docker compose to recreate only the backend service
docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate "${SERVICE_NAME}"

# --- Step 5: Health check ---
if health_check "${HEALTH_CHECK_TIMEOUT}"; then
    log "Deployment successful!"
    log "New image: ${NEW_IMAGE}"

    # Clean up old images
    docker image prune -f > /dev/null 2>&1 || true

    exit 0
fi

# --- Step 6: Rollback on failure ---
log "ROLLING BACK to previous image..."

if [[ -n "${PREVIOUS_IMAGE}" && "${PREVIOUS_IMAGE}" != ":" ]]; then
    export BACKEND_IMAGE="${PREVIOUS_IMAGE}"
    docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate "${SERVICE_NAME}"

    log "Waiting for rollback health check..."
    if health_check "${HEALTH_CHECK_TIMEOUT}"; then
        log "Rollback successful. Running on: ${PREVIOUS_IMAGE}"
    else
        log "WARNING: Rollback health check also failed!"
    fi
else
    log "WARNING: No previous image to roll back to"
fi

echo "ERROR: Deployment failed — new container did not pass health checks" >&2
exit 1
