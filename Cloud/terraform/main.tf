terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "pickup-ai"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

module "networking" {
  source = "./modules/networking"

  environment = var.environment
  vpc_cidr    = var.vpc_cidr
  azs         = var.azs
}

module "secrets" {
  source = "./modules/secrets"

  environment   = var.environment
  secret_values = {}
}

module "rds" {
  source = "./modules/rds"

  environment             = var.environment
  instance_class          = var.rds_instance_class
  allocated_storage       = var.rds_allocated_storage
  backup_retention_period = var.rds_backup_retention_period
  subnet_ids              = module.networking.private_subnet_ids
  sg_id                   = module.networking.sg_rds_id
  password                = module.secrets.db_password
}

module "ecr" {
  source = "./modules/ecr"

  repository_name = "pickup-${var.environment}"
  max_untagged    = 10
}

module "s3" {
  source = "./modules/s3"

  environment  = var.environment
  bucket_names = var.s3_bucket_names
}

module "ec2" {
  source = "./modules/ec2"

  environment        = var.environment
  instance_type      = var.ec2_instance_type
  subnet_id          = module.networking.public_subnet_ids[0]
  sg_id              = module.networking.sg_web_id
  ecr_repository_arn = module.ecr.repository_arn
  secret_arn         = module.secrets.secret_arn
  s3_bucket_arns = [
    module.s3.reports_bucket_arn,
    module.s3.audio_bucket_arn,
  ]
}
