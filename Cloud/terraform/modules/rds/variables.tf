variable "environment" {
  description = "Environment name (dev or prod)"
  type        = string
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Name of the database to create"
  type        = string
  default     = "pickup"
}

variable "subnet_ids" {
  description = "List of private subnet IDs for the DB subnet group"
  type        = list(string)
}

variable "sg_id" {
  description = "Security group ID to attach to the RDS instance"
  type        = string
}

variable "password" {
  description = "Master password for the RDS instance"
  type        = string
  sensitive   = true
}

variable "backup_retention_period" {
  description = "Number of days to retain automated backups"
  type        = number
  default     = 7
}
