# The public traffic layer: two Application Load Balancers, each with a target
# group (where it sends traffic) and an HTTP:80 listener (the front door).
# Adopt all six existing resources.

# ── API load balancer ────────────────────────────────────────────────────────
resource "aws_lb" "api" {
  name               = "docex-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.api_alb.id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "api" {
  name        = "docex-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 5
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ── Web load balancer ────────────────────────────────────────────────────────
resource "aws_lb" "web" {
  name               = "docex-web-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.web_alb.id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "web" {
  name        = "docex-web-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "ip"

  health_check {
    path                = "/"
    matcher             = "200-399"
    healthy_threshold   = 5
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "web" {
  load_balancer_arn = aws_lb.web.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

# ── Imports (IDs are the resource ARNs) ──────────────────────────────────────
import {
  to = aws_lb.api
  id = "arn:aws:elasticloadbalancing:eu-west-1:656732270414:loadbalancer/app/docex-alb/89c3c38a06b4e257"
}

import {
  to = aws_lb_target_group.api
  id = "arn:aws:elasticloadbalancing:eu-west-1:656732270414:targetgroup/docex-api-tg/1a530f773c049225"
}

import {
  to = aws_lb_listener.api
  id = "arn:aws:elasticloadbalancing:eu-west-1:656732270414:listener/app/docex-alb/89c3c38a06b4e257/956435514b45c0d9"
}

import {
  to = aws_lb.web
  id = "arn:aws:elasticloadbalancing:eu-west-1:656732270414:loadbalancer/app/docex-web-alb/c9561b75a72a645e"
}

import {
  to = aws_lb_target_group.web
  id = "arn:aws:elasticloadbalancing:eu-west-1:656732270414:targetgroup/docex-web-tg/301f4eb5059b3f7e"
}

import {
  to = aws_lb_listener.web
  id = "arn:aws:elasticloadbalancing:eu-west-1:656732270414:listener/app/docex-web-alb/c9561b75a72a645e/57cfb20d73db91ed"
}
