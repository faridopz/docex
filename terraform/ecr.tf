# Container registries holding the DOCex images.
#
# These already exist (created by hand in Module 4), so we ADOPT them with
# `import` blocks instead of creating new ones. The resource blocks describe
# what's already there; the import blocks tell Terraform their real IDs.

resource "aws_ecr_repository" "web" {
  name = "docex-web"
}

resource "aws_ecr_repository" "api" {
  name = "docex-api"
}

# import blocks (Terraform 1.5+): "this config maps to an EXISTING resource
# with this ID — adopt it into state, do not create." For ECR, the ID is just
# the repository name. These blocks are one-time: once imported, you can delete
# them. They're declarative and reviewable (unlike the old `terraform import`
# CLI command, which left no trace in your code).
import {
  to = aws_ecr_repository.web
  id = "docex-web"
}

import {
  to = aws_ecr_repository.api
  id = "docex-api"
}
