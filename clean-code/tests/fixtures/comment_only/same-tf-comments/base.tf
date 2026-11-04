# Bucket for logs.
resource "aws_s3_bucket" "logs" { // why
  bucket = "${var.prefix}-logs # not a comment"
  /* block */
  policy = <<EOT
# heredoc text, not a comment
EOT
}
