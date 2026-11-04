resource "aws_s3_bucket" "logs" {
  bucket = "${var.prefix}-logs # not a comment"
  policy = <<EOT
# heredoc text, not a comment
EOT
}
