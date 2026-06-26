# Durable object storage for uploaded documents + generated artifacts.
# Replaces the ephemeral container disk (decks/, checks/, ... which are wiped on
# every redeploy). The app stores files HERE, with metadata in the database.

resource "aws_s3_bucket" "documents" {
  bucket = "docex-documents-656732270414"
}

# Never allow public access — documents are private to their owner/tenant.
resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Keep previous versions (the "unlimited undo" for files).
resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Encrypt everything at rest.
resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

output "documents_bucket" {
  description = "S3 bucket name for the app to store documents."
  value       = aws_s3_bucket.documents.bucket
}
