# CloudWatch log groups the ECS tasks write to. Adopt the existing ones.
# (Created earlier with `aws logs create-log-group`, so no retention set =
# "never expire", which is the provider default too.)

resource "aws_cloudwatch_log_group" "api" {
  name = "/ecs/docex-api"
}

resource "aws_cloudwatch_log_group" "web" {
  name = "/ecs/docex-web"
}

import {
  to = aws_cloudwatch_log_group.api
  id = "/ecs/docex-api"
}

import {
  to = aws_cloudwatch_log_group.web
  id = "/ecs/docex-web"
}
