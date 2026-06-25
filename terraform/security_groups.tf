# The four firewalls (security groups). Two per service: one for the public
# ALB (open on 80), one for the tasks (reachable ONLY from their ALB).
#
# Each block declares the ingress rule we added PLUS the default "allow all
# outbound" egress rule AWS auto-creates — both must be present for a clean,
# no-change import. Descriptions must match exactly (they're immutable).

# ── API side ────────────────────────────────────────────────────────────────
resource "aws_security_group" "api_alb" {
  name        = "docex-alb-sg"
  description = "DOCex ALB"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "api" {
  name        = "docex-api-sg"
  description = "DOCex API tasks"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.api_alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── Web side ────────────────────────────────────────────────────────────────
resource "aws_security_group" "web_alb" {
  name        = "docex-web-alb-sg"
  description = "DOCex web ALB"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "web" {
  name        = "docex-web-sg"
  description = "DOCex web tasks"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.web_alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── Import the existing groups by their IDs ──────────────────────────────────
import {
  to = aws_security_group.api_alb
  id = "sg-09f643b04d530d2ed"
}

import {
  to = aws_security_group.api
  id = "sg-00aee2da4acb27a2c"
}

import {
  to = aws_security_group.web_alb
  id = "sg-0b16d990fe20d6b06"
}

import {
  to = aws_security_group.web
  id = "sg-03aa165787191c72e"
}
