resource "aws_db_subnet_group" "this" {
  name       = "pickup-${var.environment}-db-subnet-group"
  subnet_ids = var.subnet_ids

  tags = {
    Name = "pickup-${var.environment}-db-subnet-group"
  }
}

resource "aws_db_instance" "this" {
  identifier     = "pickup-${var.environment}"
  engine         = "postgres"
  engine_version = "16"

  instance_class    = var.instance_class
  allocated_storage = var.allocated_storage

  db_name  = var.db_name
  username = "pickup"
  password = var.password

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.sg_id]

  storage_encrypted   = true
  multi_az            = false
  publicly_accessible = false

  backup_retention_period = var.backup_retention_period
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:30-sun:05:30"

  skip_final_snapshot       = var.environment == "dev"
  final_snapshot_identifier = var.environment == "prod" ? "pickup-${var.environment}-final" : null

  tags = {
    Name = "pickup-${var.environment}-db"
  }
}
