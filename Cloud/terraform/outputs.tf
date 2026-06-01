output "vpc_id" {
  description = "ID of the VPC"
  value       = module.networking.vpc_id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = module.networking.public_subnet_ids
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = module.networking.private_subnet_ids
}

output "sg_web_id" {
  description = "ID of the web security group"
  value       = module.networking.sg_web_id
}

output "sg_rds_id" {
  description = "ID of the RDS security group"
  value       = module.networking.sg_rds_id
}

# RDS outputs
output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = module.rds.endpoint
}

output "rds_port" {
  description = "RDS instance port"
  value       = module.rds.port
}

output "rds_db_name" {
  description = "RDS database name"
  value       = module.rds.db_name
}

# Secrets Manager outputs
output "secret_arn" {
  description = "ARN of the Secrets Manager secret"
  value       = module.secrets.secret_arn
}

output "secret_name" {
  description = "Name of the Secrets Manager secret"
  value       = module.secrets.secret_name
}

# ECR outputs
output "ecr_repository_url" {
  description = "URL of the ECR repository"
  value       = module.ecr.repository_url
}

output "ecr_repository_arn" {
  description = "ARN of the ECR repository"
  value       = module.ecr.repository_arn
}

# S3 outputs
output "s3_reports_bucket_name" {
  description = "Name of the reports S3 bucket"
  value       = module.s3.reports_bucket_name
}

output "s3_audio_bucket_name" {
  description = "Name of the audio S3 bucket"
  value       = module.s3.audio_bucket_name
}

output "s3_reports_bucket_arn" {
  description = "ARN of the reports S3 bucket"
  value       = module.s3.reports_bucket_arn
}

output "s3_audio_bucket_arn" {
  description = "ARN of the audio S3 bucket"
  value       = module.s3.audio_bucket_arn
}

# EC2 outputs
output "ec2_instance_id" {
  description = "ID of the EC2 instance"
  value       = module.ec2.instance_id
}

output "ec2_public_ip" {
  description = "Public IP of the EC2 instance"
  value       = module.ec2.public_ip
}
