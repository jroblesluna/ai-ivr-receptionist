# Requirements Document

## Introduction

Migration of the PickUp AI IVR Receptionist application from Railway to AWS. The migration covers infrastructure provisioning with Terraform, database migration from SQLite to PostgreSQL, in-memory state externalization to Redis, file storage migration to S3, secrets management via AWS Secrets Manager, and CI/CD automation with GitHub Actions. The AlwaysPrint project serves as the reference architecture for Terraform module structure and deployment patterns.

## Glossary

- **PickUp_System**: The AI IVR Receptionist Flask application including API endpoints (Twilio webhooks) and admin UI
- **Terraform_IaC**: Infrastructure as Code modules that provision and manage all AWS resources
- **CI_CD_Pipeline**: GitHub Actions workflows that build, test, and deploy the application
- **Session_Store**: Redis-based storage for active call state (conversations, collected info, outbound calls)
- **Database**: PostgreSQL RDS instance managed by Alembic migrations
- **File_Storage**: S3 buckets for persistent file storage (reports, audio assets)
- **Secrets_Manager**: AWS Secrets Manager service storing application credentials
- **Deploy_Script**: Shell script on EC2 that pulls new Docker images from ECR and restarts services
- **Docker_Compose_Stack**: The set of containers running on EC2 (backend, Redis, Nginx, Certbot)
- **DEV_Environment**: Development environment at pickup.dev.iol.pe
- **PROD_Environment**: Production environment at pickup.apps.iol.pe

## Requirements

### Requirement 1: Terraform Infrastructure Modules

**User Story:** As a DevOps engineer, I want all AWS infrastructure defined as Terraform modules, so that environments are reproducible and version-controlled.

#### Acceptance Criteria

1. THE Terraform_IaC SHALL provision a VPC with a minimum of 2 public subnets and 2 private subnets across 2 Availability Zones, an internet gateway, a NAT gateway for private subnet outbound traffic, and security groups that allow inbound HTTPS (port 443) and HTTP (port 80) to the public subnet and inbound PostgreSQL (port 5432) from the public subnet security group to the private subnet security group only
2. THE Terraform_IaC SHALL provision an ECR repository for the PickUp_System Docker images with an image lifecycle policy that retains a maximum of 10 untagged images
3. THE Terraform_IaC SHALL provision an RDS PostgreSQL 16 instance in a private subnet with instance class and allocated storage configurable per environment via tfvars, automated backups enabled with a retention period of 7 days, and encryption at rest enabled
4. THE Terraform_IaC SHALL provision an EC2 instance with instance type configurable per environment via tfvars and an IAM role granting ECR pull, Secrets Manager read, S3 read and write access scoped to the provisioned report and audio buckets only, and SSM managed instance permissions
5. THE Terraform_IaC SHALL provision two S3 buckets: one for reports and one for audio asset storage, both with versioning enabled and public access blocked
6. THE Terraform_IaC SHALL provision secrets in AWS Secrets Manager with randomly generated database passwords of at least 24 characters including uppercase, lowercase, digits, and special characters
7. THE Terraform_IaC SHALL support per-environment configuration via separate tfvars files (dev.tfvars, prod.tfvars) containing at minimum the EC2 instance type, RDS instance class, RDS allocated storage, and environment domain name
8. THE Terraform_IaC SHALL use Terraform workspaces for state isolation between DEV_Environment and PROD_Environment
9. THE Terraform_IaC SHALL configure EC2 access exclusively via SSM Session Manager with no SSH key pairs and no security group rules allowing inbound SSH (port 22)
10. THE Terraform_IaC SHALL store Terraform state in a remote S3 backend with DynamoDB state locking enabled
11. IF terraform plan is executed against an existing environment, THEN THE Terraform_IaC SHALL produce no changes unless module source code has been modified

### Requirement 2: Database Migration to PostgreSQL

**User Story:** As a developer, I want the application to use PostgreSQL with proper migration tooling, so that the database is reliable, scalable, and schema changes are tracked.

#### Acceptance Criteria

1. THE PickUp_System SHALL connect to the Database using SQLAlchemy with connection pooling configured with a minimum of 2 and a maximum of 10 connections
2. THE Database SHALL contain all tables currently in SQLite (config, reports, use_cases, topics, roles, users, user_use_cases, caller_profiles) with equivalent column types mapped to PostgreSQL-native types
3. WHEN the application starts, THE PickUp_System SHALL apply pending Alembic migrations automatically and log each migration version applied
4. IF an Alembic migration fails during application startup, THEN THE PickUp_System SHALL halt startup, log an error message indicating the failed migration version, and exit with a non-zero status code without serving requests
5. THE Database SHALL enforce foreign key constraints (topics→use_cases, users→roles, user_use_cases→users, user_use_cases→use_cases, caller_profiles→use_cases) and unique constraints (config.key, users.email, roles.name, use_cases.id, topics(use_case_id, key), caller_profiles(phone, use_case_id)) matching the current SQLite schema
6. WHEN a database connection fails, THE PickUp_System SHALL retry the connection with exponential backoff starting at 1 second and doubling each attempt, up to a maximum of 3 attempts
7. IF all 3 database connection retry attempts are exhausted, THEN THE PickUp_System SHALL log an error message indicating connection failure and raise an exception that prevents the application from starting

### Requirement 3: Session State Externalization to Redis

**User Story:** As a developer, I want active call state stored in Redis, so that the application supports multiple workers and state persists across deployments.

#### Acceptance Criteria

1. THE Session_Store SHALL store each call session as a serialized record containing: conversation history (capped at 50 messages per session), collected caller info (name, phone, notes, topic, lang), outbound call mappings, failed rooms, briefed rooms, machine detection counts, and intro-played flags
2. WHEN a call session is created, THE Session_Store SHALL set a TTL of 2 hours on the session data
3. THE PickUp_System SHALL read and write call state exclusively through the Session_Store instead of in-memory Python dictionaries
4. IF the Session_Store is unavailable during a call webhook request, THEN THE PickUp_System SHALL log the connection error and return a TwiML response that plays an apology message and hangs up the call within 5 seconds
5. THE PickUp_System SHALL support running with at least 2 concurrent Gunicorn workers where any worker can serve any call webhook and retrieve the correct session state from the Session_Store
6. IF a session key is not found in the Session_Store when a call webhook references it, THEN THE PickUp_System SHALL treat the call as a new session and initialize a fresh session record

### Requirement 4: Docker Compose Deployment Stack

**User Story:** As a DevOps engineer, I want the application deployed as a Docker Compose stack on EC2, so that all services are co-located and manageable.

#### Acceptance Criteria

1. THE Docker_Compose_Stack SHALL include containers for the PickUp_System backend, Redis, Nginx, and Certbot
2. THE PickUp_System container SHALL include ffmpeg for audio processing
3. THE Docker_Compose_Stack SHALL configure Nginx as a reverse proxy that forwards HTTP requests to the PickUp_System container with TLS termination using Let's Encrypt certificates, and SHALL automatically renew certificates before expiry via the Certbot container
4. WHEN the EC2 instance is first provisioned, THE Terraform_IaC SHALL install Docker and Docker Compose via user_data script
5. THE Docker_Compose_Stack SHALL pass database connection strings and application secrets as environment variables retrieved from Secrets_Manager by the Deploy_Script at deployment time
6. THE PickUp_System container SHALL run Gunicorn with the number of workers configured via an environment variable, with a minimum of 2 workers in PROD_Environment and a default of 1 worker in DEV_Environment, and a request timeout of 120 seconds
7. THE Docker_Compose_Stack SHALL configure all containers with a restart policy of "unless-stopped" so that containers automatically recover after crashes or host reboots
8. THE Docker_Compose_Stack SHALL define health checks for the PickUp_System and Redis containers, where a container is considered unhealthy if it fails to respond within 10 seconds for 3 consecutive checks

### Requirement 5: CI/CD Pipeline with GitHub Actions

**User Story:** As a developer, I want automated deployments triggered by code changes, so that releases are consistent and require minimal manual intervention.

#### Acceptance Criteria

1. WHEN code is pushed to the main branch and the push includes changes to files outside of `*.md`, `docs/**`, and `terraform/**` paths, THE CI_CD_Pipeline SHALL automatically build and deploy to the DEV_Environment
2. WHEN a manual workflow_dispatch is triggered, THE CI_CD_Pipeline SHALL deploy to the PROD_Environment
3. THE CI_CD_Pipeline SHALL build the Docker image, push it to ECR, and invoke the Deploy_Script on EC2 via SSM send-command with a timeout of 300 seconds
4. THE Deploy_Script SHALL pull the latest image from ECR, start the new container, verify it passes health checks within 60 seconds, and stop the old container only after the new container is healthy
5. IF the Docker image build fails, THEN THE CI_CD_Pipeline SHALL mark the workflow run as failed and halt deployment without invoking the Deploy_Script
6. IF the SSM send-command fails or times out, THEN THE CI_CD_Pipeline SHALL mark the workflow run as failed and report which deployment step failed
7. IF the Deploy_Script detects that the new container fails health checks, THEN THE Deploy_Script SHALL roll back to the previous image and report the failure to the CI_CD_Pipeline

### Requirement 6: Secrets Management

**User Story:** As a security engineer, I want all application secrets stored in AWS Secrets Manager, so that credentials are centrally managed and rotatable without code changes.

#### Acceptance Criteria

1. THE Secrets_Manager SHALL store Twilio credentials (account SID, auth token, API key SID, API key secret, TwiML app SID, Verify SID), OpenAI API key, Resend API key, ElevenLabs API key, Google TTS API key, and the database password as key-value pairs within a single AWS Secrets Manager secret per environment
2. WHEN the PickUp_System starts, THE PickUp_System SHALL retrieve all secrets from Secrets_Manager within 10 seconds and load them into application memory for use by service modules
3. THE PickUp_System SHALL remove the Fernet encryption layer and SECRET_KEY dependency for credential storage, reading all credentials exclusively from Secrets_Manager
4. IF the Secrets_Manager is unreachable or returns an error during startup, THEN THE PickUp_System SHALL terminate the process within 10 seconds and log an error message indicating the secret name that failed and the connection error reason
5. THE Terraform_IaC SHALL create one Secrets_Manager secret for DEV_Environment and one separate Secrets_Manager secret for PROD_Environment, each containing the full set of credential keys defined in criterion 1
6. WHEN a secret value is updated in Secrets_Manager, THE PickUp_System SHALL use the updated value upon its next restart without requiring any code or configuration file changes

### Requirement 7: File Storage Migration to S3

**User Story:** As a developer, I want reports and audio assets stored in S3, so that files persist independently of the EC2 instance and are accessible across deployments.

#### Acceptance Criteria

1. WHEN a call report is generated, THE PickUp_System SHALL upload the JSON report file and associated audio files (MP3) to the File_Storage within 30 seconds of report generation
2. WHEN a report is requested via the admin UI, THE PickUp_System SHALL retrieve the report JSON from the File_Storage and return it to the client; IF the retrieval fails, THEN THE PickUp_System SHALL return an HTTP 503 response with an error message
3. THE File_Storage SHALL store audio assets (WAV files for hold music and intro) in a dedicated S3 prefix accessible to the PickUp_System via IAM role permissions
4. THE PickUp_System SHALL serve audio assets to Twilio via pre-signed S3 URLs with an expiration time of 1 hour
5. WHEN an S3 upload fails, THE PickUp_System SHALL retry the upload up to 2 times with a 1-second delay between attempts before logging the error and continuing without blocking the call flow

### Requirement 8: Environment and Domain Configuration

**User Story:** As a DevOps engineer, I want separate DEV and PROD environments with distinct domains, so that development changes are isolated from production traffic.

#### Acceptance Criteria

1. THE DEV_Environment SHALL be accessible via HTTPS at pickup.dev.iol.pe and return a successful response within 5 seconds
2. THE PROD_Environment SHALL be accessible via HTTPS at pickup.apps.iol.pe and return a successful response within 5 seconds
3. THE Docker_Compose_Stack SHALL configure Nginx with the environment's assigned domain and a valid, non-expired TLS certificate that matches that domain for each environment
4. THE Terraform_IaC SHALL provision infrastructure stacks for DEV_Environment and PROD_Environment with no shared compute, database, or network resources between them
5. WHEN deploying to DEV_Environment, THE CI_CD_Pipeline SHALL use dev-specific secrets and database instance
6. WHEN deploying to PROD_Environment, THE CI_CD_Pipeline SHALL use prod-specific secrets and database instance
7. IF a deployment target does not match the pipeline's designated environment, THEN THE CI_CD_Pipeline SHALL reject the deployment and report an error message indicating an environment mismatch

### Requirement 9: Data Migration from Current Platform

**User Story:** As a developer, I want existing data migrated from the Railway deployment, so that no call history, configuration, or user accounts are lost.

#### Acceptance Criteria

1. THE PickUp_System SHALL provide a migration script that exports SQLite data and imports it into the Database
2. THE migration script SHALL transfer all use cases, topics, users (including password hashes), roles, user_use_cases assignments, caller profiles, non-encrypted config entries, and report index records
3. THE migration script SHALL decrypt Fernet-encrypted config values (keys prefixed with _sec_) and re-store them in Secrets_Manager
4. WHEN the migration script encounters a record that fails to import, THE migration script SHALL log the table name, record identifier, and error reason to standard output, then continue processing remaining records
5. THE migration script SHALL transfer report JSON files and audio recordings (MP3) from the Railway volume to the File_Storage
6. WHEN the migration script completes, THE migration script SHALL output a summary reporting the number of records migrated and the number of records failed per table
7. IF the migration script is run against a Database that already contains migrated data, THEN THE migration script SHALL skip existing records without creating duplicates
8. WHEN the migration script completes with zero failed records, THE migration script SHALL exit with code 0; IF any records failed, THEN THE migration script SHALL exit with a non-zero exit code
