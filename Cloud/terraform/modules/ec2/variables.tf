variable "environment" {
  description = "Environment name (dev or prod)"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "subnet_id" {
  description = "Public subnet ID for the EC2 instance"
  type        = string
}

variable "sg_id" {
  description = "Security group ID for the EC2 instance"
  type        = string
}

variable "ecr_repository_arn" {
  description = "ARN of the ECR repository for pull permissions"
  type        = string
}

variable "secret_arn" {
  description = "ARN of the Secrets Manager secret for read permissions"
  type        = string
}

variable "s3_bucket_arns" {
  description = "List of S3 bucket ARNs for read/write permissions"
  type        = list(string)
}
