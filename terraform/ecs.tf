# The task definitions (blueprints) and services (the running app).
#
# Task definitions: we DEFINE them here (not import) — they're immutable,
# versioned artifacts, so Terraform owns the template and registers revisions.
# The JSON mirrors what's running today, so the new revision is functionally
# identical. Image stays ":latest" so the CI/CD pipeline keeps owning deploys.
#
# Services: we IMPORT the existing ones and point them at the Terraform task
# defs. On apply they roll onto the new revision with zero downtime.

# ── API task definition ──────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "api" {
  family                   = "docex-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_exec.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name         = "docex-api"
      image        = "656732270414.dkr.ecr.eu-west-1.amazonaws.com/docex-api:latest"
      essential    = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment = [
        { name = "PORT", value = "8000" },
        { name = "ALLOWED_ORIGINS", value = "http://docex-web-alb-926754058.eu-west-1.elb.amazonaws.com" }
      ]
      secrets = [
        { name = "ANTHROPIC_API_KEY", valueFrom = data.aws_secretsmanager_secret.anthropic.arn }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/docex-api"
          "awslogs-region"        = "eu-west-1"
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

# ── Web task definition ──────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "web" {
  family                   = "docex-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_exec.arn

  container_definitions = jsonencode([
    {
      name         = "docex-web"
      image        = "656732270414.dkr.ecr.eu-west-1.amazonaws.com/docex-web:latest"
      essential    = true
      portMappings = [{ containerPort = 3000, protocol = "tcp" }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/docex-web"
          "awslogs-region"        = "eu-west-1"
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

# ── API service ──────────────────────────────────────────────────────────────
resource "aws_ecs_service" "api" {
  name            = "docex-api"
  cluster         = aws_ecs_cluster.docex.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  # Preserve the AWS-default AZ rebalancing (omitting it would disable it).
  availability_zone_rebalancing = "ENABLED"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "docex-api"
    container_port   = 8000
  }

  health_check_grace_period_seconds = 90
}

# ── Web service ──────────────────────────────────────────────────────────────
resource "aws_ecs_service" "web" {
  name            = "docex-web"
  cluster         = aws_ecs_cluster.docex.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  # Preserve the AWS-default AZ rebalancing (omitting it would disable it).
  availability_zone_rebalancing = "ENABLED"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.web.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "docex-web"
    container_port   = 3000
  }

  health_check_grace_period_seconds = 90
}

import {
  to = aws_ecs_service.api
  id = "docex-cluster/docex-api"
}

import {
  to = aws_ecs_service.web
  id = "docex-cluster/docex-web"
}
