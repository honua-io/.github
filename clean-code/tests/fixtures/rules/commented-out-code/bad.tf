# resource "aws_s3_bucket" "logs" {
locals {
  retries = 3
}
