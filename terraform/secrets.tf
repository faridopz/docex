# The Anthropic API key secret. We DON'T manage it with Terraform (that would
# risk putting the value in state). Instead a `data` source just READS its
# metadata (the ARN), so the task definition can reference it. Data sources
# need no import — they look up an existing thing every run.

data "aws_secretsmanager_secret" "anthropic" {
  arn = "arn:aws:secretsmanager:eu-west-1:656732270414:secret:docex/anthropic-api-key-5lKZ9n"
}
