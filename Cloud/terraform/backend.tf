terraform {
  backend "s3" {
    bucket         = "pickup-ai-tf-state-040982"
    key            = "infrastructure/terraform.tfstate"
    region         = "us-west-2"
    dynamodb_table = "pickup-ai-terraform-locks"
    encrypt        = true

    workspace_key_prefix = "env"
  }
}
