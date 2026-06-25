# The default VPC and its subnets. AWS created these for the account; we just
# REFERENCE them (data sources), we don't manage them. The security groups,
# load balancers, and services all need these IDs.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}
