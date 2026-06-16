output "archive_lambda_arn" {
  value = aws_lambda_function.archive_handler.arn
}

output "archive_lambda_name" {
  value = aws_lambda_function.archive_handler.function_name
}
