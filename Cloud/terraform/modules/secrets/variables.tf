variable "environment" {
  description = "Environment name (dev or prod)"
  type        = string
}

variable "secret_values" {
  description = "Map of secret key-value pairs to store in Secrets Manager"
  type        = map(string)
  sensitive   = true
  default     = {}
}
