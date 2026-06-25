# The ECS task execution role — what ECS uses to pull images, write logs, and
# read the secret. Adopt the existing role + its two policies.
#
# Note `jsonencode({...})`: we write the policy as native HCL and Terraform
# turns it into the JSON AWS expects. Cleaner and less error-prone than raw
# JSON strings, and it must match the live policy exactly for a no-change import.

resource "aws_iam_role" "ecs_exec" {
  name = "docexEcsTaskExecutionRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# The AWS-managed policy (ECR pull + CloudWatch logs), attached to the role.
resource "aws_iam_role_policy_attachment" "ecs_exec_managed" {
  role       = aws_iam_role.ecs_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Our inline least-privilege policy: read ONLY the DOCex secret.
resource "aws_iam_role_policy" "ecs_exec_secrets" {
  name = "docex-secrets-read"
  role = aws_iam_role.ecs_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = "arn:aws:secretsmanager:eu-west-1:656732270414:secret:docex/anthropic-api-key-5lKZ9n"
    }]
  })
}

# Import blocks. Note the different ID formats per resource type:
import {
  to = aws_iam_role.ecs_exec
  id = "docexEcsTaskExecutionRole"
}

import {
  to = aws_iam_role_policy_attachment.ecs_exec_managed
  id = "docexEcsTaskExecutionRole/arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

import {
  to = aws_iam_role_policy.ecs_exec_secrets
  id = "docexEcsTaskExecutionRole:docex-secrets-read"
}
