# Implementation Plan: AWS Migration

## Overview

Migrate the PickUp AI IVR Receptionist from Railway to AWS. The implementation follows an infrastructure-first approach: provision AWS resources with Terraform, refactor the application layer (database, session, storage, config), containerize with Docker, set up CI/CD, and finally create the data migration script. All code is Python, infrastructure is Terraform/HCL, and CI/CD uses GitHub Actions YAML.

## Tasks

- [x] 1. Terraform infrastructure modules
  - [x] 1.1 Create Terraform project structure and networking module
    - Create `Cloud/terraform/` directory with `main.tf`, `variables.tf`, `outputs.tf`, `backend.tf`, `dev.tfvars`, `prod.tfvars`, and `setup.sh`
    - Implement `modules/networking/` with VPC (10.0.0.0/16), 2 public subnets, 2 private subnets across 2 AZs, internet gateway, NAT gateway, route tables
    - Define security groups: `sg-web` (inbound 80, 443), `sg-rds` (inbound 5432 from sg-web only), no SSH rules
    - _Requirements: 1.1, 1.9_

  - [x] 1.2 Create ECR and S3 Terraform modules
    - Implement `modules/ecr/` with repository and lifecycle policy (max 10 untagged images)
    - Implement `modules/s3/` with two buckets (reports + audio), versioning enabled, public access blocked
    - _Requirements: 1.2, 1.5_

  - [x] 1.3 Create RDS and Secrets Manager Terraform modules
    - Implement `modules/rds/` with PostgreSQL 16, private subnet placement, encryption at rest, 7-day backup retention, configurable instance class and storage via tfvars
    - Implement `modules/secrets/` with one secret per environment containing all credential keys, randomly generated DB password (24+ chars with uppercase, lowercase, digits, special chars)
    - _Requirements: 1.3, 1.6, 1.5_

  - [x] 1.4 Create EC2 Terraform module and compose root configuration
    - Implement `modules/ec2/` with configurable instance type, IAM role (ECR pull, Secrets Manager read, S3 read/write scoped to provisioned buckets, SSM managed instance), user_data.sh.tpl that installs Docker + Docker Compose
    - Wire all modules together in `main.tf`, configure S3 remote state backend with DynamoDB locking in `backend.tf`
    - Support workspace-based state isolation (dev/prod)
    - _Requirements: 1.4, 1.7, 1.8, 1.9, 1.10, 1.11_

- [x] 2. Checkpoint - Validate Terraform
  - Ensure `terraform validate` passes for all modules, ask the user if questions arise.

- [x] 3. Database layer refactoring with SQLAlchemy + Alembic
  - [x] 3.1 Create SQLAlchemy models package
    - Create `src/models/__init__.py` with Base, engine factory (pool_size=2, max_overflow=8, pool_pre_ping=True, pool_recycle=3600), Session factory, and startup retry logic (exponential backoff 1s→2s→4s, 3 attempts max)
    - Create `src/models/config.py` (Config model), `src/models/report.py` (Report model), `src/models/use_case.py` (UseCase + Topic models with relationships), `src/models/user.py` (User, Role, UserUseCase models), `src/models/caller_profile.py` (CallerProfile model)
    - Enforce all foreign key and unique constraints matching current SQLite schema
    - _Requirements: 2.1, 2.2, 2.5_

  - [x] 3.2 Set up Alembic and create initial migration
    - Initialize Alembic in `src/alembic/` with `env.py` configured to use the SQLAlchemy engine
    - Create `001_initial_schema.py` migration capturing the full PostgreSQL schema
    - Add auto-migration at app startup (`alembic upgrade head`) with error handling: log failed version and `SystemExit(1)` on failure
    - _Requirements: 2.3, 2.4_

  - [x] 3.3 Refactor `src/db.py` to delegate to SQLAlchemy models
    - Rewrite all functions in `src/db.py` to use SQLAlchemy sessions instead of raw sqlite3
    - Maintain the same public function API (config_get, config_set, report_insert, uc_list, user_create, etc.) so existing route code continues to work
    - Implement connection retry with exponential backoff (1s→2s→4s, 3 attempts)
    - Remove `init()` bootstrap (replaced by Alembic), remove Fernet encryption functions
    - _Requirements: 2.1, 2.5, 2.6, 2.7_

  - [x] 3.4 Write property test for database connection retry logic
    - **Property 4: Data migration preserves all records** (partial — validates model round-trip)
    - **Validates: Requirements 2.6, 2.7**

- [x] 4. Redis session store implementation
  - [x] 4.1 Implement `src/session_store.py` with Redis backend
    - Create `SessionStore` class with all methods from design (get/set_conversation, get/set_collected_info, add_outbound_call, mark_failed_room, mark_briefed_room, get/increment_machine_count, mark_intro_played, has_intro_played)
    - Use Redis key patterns with 2-hour TTL on all keys
    - Cap conversation history at 50 messages
    - Handle Redis unavailability: log error, return TwiML apology + hangup within 5s
    - Handle missing session keys: initialize fresh session record
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 4.2 Replace all `state.py` references with `SessionStore` calls
    - Update all route files (`routes/ai.py`, `routes/operator.py`, `routes/menu.py`) to use `SessionStore` instead of importing from `state.py`
    - Ensure multi-worker compatibility (no in-memory state)
    - _Requirements: 3.3, 3.5_

  - [x] 4.3 Write property test for session state round-trip
    - **Property 1: Session state round-trip preservation**
    - **Validates: Requirements 3.1**

- [x] 5. Checkpoint - Validate core refactoring
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Config module and S3 storage
  - [x] 6.1 Refactor `src/config.py` to use AWS Secrets Manager
    - Implement `SecretsConfig` class that fetches all secrets from Secrets Manager at startup and caches in memory
    - Rewrite accessor functions (account_sid, auth_token, etc.) to delegate to `SecretsConfig.get()`
    - Remove Fernet encryption dependency and SECRET_KEY for credential storage
    - Retain SECRET_KEY in Secrets Manager for Flask session signing
    - Handle Secrets Manager unreachable: terminate within 10s with error log
    - Add env var fallback for local development (when `AWS_REGION` is not set)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_

  - [x] 6.2 Implement `src/storage.py` with S3 backend
    - Create `S3Storage` class with methods: upload_report, upload_audio, get_report, get_audio_url, upload_with_retry
    - S3 key structure: `reports/{id}.json`, `reports/{id}.mp3`, `reports/{id}.recording.mp3` for reports bucket; `assets/*.wav` for audio bucket
    - Implement retry logic (2 retries, 1s delay) for uploads
    - Handle download failures with HTTP 503
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 6.3 Refactor `src/reports.py` and `src/routes/media.py` to use S3Storage
    - Update `reports.py` to upload JSON + MP3 to S3 instead of local filesystem
    - Update `routes/media.py` to redirect to pre-signed S3 URLs (1-hour expiry) instead of serving local files
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 6.4 Write property test for report storage round-trip
    - **Property 2: Report storage round-trip preservation**
    - **Validates: Requirements 7.2**

  - [x] 6.5 Write property test for pre-signed URL correctness
    - **Property 3: Pre-signed URL correctness**
    - **Validates: Requirements 7.4**

- [x] 7. Health check endpoint
  - [x] 7.1 Add `/health` endpoint to Flask app
    - Create health check route returning JSON with status, database connectivity, Redis connectivity, and timestamp
    - Return HTTP 200 when all checks pass, HTTP 503 when any dependency is down
    - Register in `app.py`
    - _Requirements: 4.8, 5.4_

- [x] 8. Docker and Docker Compose configuration
  - [x] 8.1 Create Dockerfile and Docker Compose stack
    - Create `Dockerfile` with python:3.11-slim base, ffmpeg, requirements install, source copy, Gunicorn CMD with configurable workers
    - Create `docker-compose.yml` with services: backend (port 8000, health check), redis (7-alpine, health check), nginx (ports 80/443, TLS), certbot
    - Configure restart policy "unless-stopped" for all containers
    - Configure health checks (10s timeout, 3 consecutive failures = unhealthy)
    - Backend workers configurable via env var (default 1 for DEV, min 2 for PROD)
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 4.8_

  - [x] 8.2 Create Nginx configuration and deploy script
    - Create `nginx/nginx.conf` with reverse proxy to backend, TLS termination with Let's Encrypt certs, certbot renewal support
    - Create `scripts/deploy.sh` that pulls latest ECR image, starts new container, health checks (60s timeout), stops old container on success, rolls back on failure
    - _Requirements: 4.3, 5.4, 5.7_

- [x] 9. GitHub Actions CI/CD workflows
  - [x] 9.1 Create DEV and PROD deployment workflows
    - Create `.github/workflows/deploy-backend-dev.yml`: triggers on push to main (path filter excludes `*.md`, `docs/**`, `terraform/**`), builds Docker image, pushes to ECR with commit SHA tag, SSM send-command to EC2 (timeout 300s)
    - Create `.github/workflows/deploy-backend-prod.yml`: triggers on workflow_dispatch only, same build+deploy flow targeting PROD
    - Configure AWS credentials, ECR login, environment-specific secrets and targets
    - Handle failures: halt on build failure, report SSM timeout, environment mismatch rejection
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 8.5, 8.6, 8.7_

- [x] 10. Checkpoint - Validate Docker and CI/CD
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Data migration script
  - [x] 11.1 Create `scripts/migrate_railway_to_aws.py`
    - Connect to source SQLite DB and target PostgreSQL via SQLAlchemy
    - Migrate tables in dependency order: roles → users → use_cases → topics → user_use_cases → caller_profiles → config → reports
    - Decrypt Fernet-encrypted config values (keys prefixed with `_sec_`) and store in Secrets Manager
    - Upload report files (JSON + MP3) to S3 reports bucket
    - Handle idempotency: skip existing records without creating duplicates
    - Log table name + record ID + error on individual record failures, continue processing
    - Output summary with counts per table (migrated/failed)
    - Exit code 0 on full success, non-zero if any records failed
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

  - [x] 11.2 Write property test for Fernet decryption round-trip
    - **Property 5: Fernet decryption round-trip during migration**
    - **Validates: Requirements 9.3**

  - [x] 11.3 Write property test for migration idempotency
    - **Property 6: Migration idempotency**
    - **Validates: Requirements 9.7**

- [x] 12. Environment configuration and documentation
  - [x] 12.1 Update `.env.example` and add `alembic.ini`
    - Update `.env.example` with new variables: DATABASE_URL, REDIS_URL, AWS_REGION, AWS_SECRET_NAME, S3_REPORTS_BUCKET, S3_AUDIO_BUCKET, GUNICORN_WORKERS, ENVIRONMENT
    - Retain existing secret keys for local development fallback
    - Create `alembic.ini` with PostgreSQL connection string placeholder
    - _Requirements: 1.7, 8.1, 8.2_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The AlwaysPrint project serves as reference for Terraform module structure, Docker Compose patterns, and GitHub Actions workflows
- Python is the implementation language throughout (matching the existing codebase)
- Local development uses env var fallbacks; AWS services are only required in deployed environments

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "3.2"] },
    { "id": 2, "tasks": ["1.4", "3.3", "4.1"] },
    { "id": 3, "tasks": ["3.4", "4.2", "6.1"] },
    { "id": 4, "tasks": ["4.3", "6.2", "7.1"] },
    { "id": 5, "tasks": ["6.3", "6.4", "6.5", "8.1"] },
    { "id": 6, "tasks": ["8.2", "9.1"] },
    { "id": 7, "tasks": ["11.1", "12.1"] },
    { "id": 8, "tasks": ["11.2", "11.3"] }
  ]
}
```
