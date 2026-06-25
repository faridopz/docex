# DOCex infrastructure as code — provider configuration.
#
# This file sets up Terraform + the AWS provider. The actual resources live in
# topic files (ecr.tf, then ecs.tf, alb.tf, etc.). We ADOPT the existing live
# resources via `import` blocks, so nothing is recreated or disrupted.

# Tell Terraform which "providers" (cloud plugins) this config needs.
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Configure the AWS provider. It automatically uses the SAME credentials your
# AWS CLI uses (~/.aws), so no keys live in this file.
provider "aws" {
  region = "eu-west-1"
}
