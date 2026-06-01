variable "environment" {
  description = "Environment name (dev or prod)"
  type        = string
}

variable "bucket_names" {
  description = "Map of logical bucket names to actual bucket name suffixes"
  type        = map(string)
  default = {
    reports = "reports"
    audio   = "audio"
  }
}
