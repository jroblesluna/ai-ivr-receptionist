variable "repository_name" {
  description = "Name of the ECR repository"
  type        = string
}

variable "max_untagged" {
  description = "Maximum number of untagged images to retain"
  type        = number
  default     = 10
}
