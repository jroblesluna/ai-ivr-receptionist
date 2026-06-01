output "secret_arn" {
  description = "ARN of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.this.arn
}

output "secret_name" {
  description = "Name of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.this.name
}

output "db_password" {
  description = "The randomly generated database password"
  value       = random_password.db.result
  sensitive   = true
}
