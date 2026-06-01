output "reports_bucket_name" {
  description = "Name of the reports S3 bucket"
  value       = aws_s3_bucket.reports.id
}

output "audio_bucket_name" {
  description = "Name of the audio S3 bucket"
  value       = aws_s3_bucket.audio.id
}

output "reports_bucket_arn" {
  description = "ARN of the reports S3 bucket"
  value       = aws_s3_bucket.reports.arn
}

output "audio_bucket_arn" {
  description = "ARN of the audio S3 bucket"
  value       = aws_s3_bucket.audio.arn
}
