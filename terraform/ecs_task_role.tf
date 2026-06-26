# The TASK role — the identity the running app code assumes to call AWS APIs
# (distinct from the EXECUTION role, which only pulls images, reads the startup
# secret, and writes logs). This is what lets the docex-api container itself
# read and write the documents bucket at runtime.

resource "aws_iam_role" "ecs_task" {
  name = "docexEcsTaskRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Least-privilege: only the documents bucket, only object + list actions.
resource "aws_iam_role_policy" "ecs_task_s3" {
  name = "docex-s3-documents"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
      Resource = [
        aws_s3_bucket.documents.arn,
        "${aws_s3_bucket.documents.arn}/*"
      ]
    }]
  })
}
