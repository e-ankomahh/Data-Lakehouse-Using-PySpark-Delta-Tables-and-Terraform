output "glue_execution_role_arn" {
  value = aws_iam_role.glue_execution.arn
}

output "step_functions_role_arn" {
  value = aws_iam_role.step_functions.arn
}

output "eventbridge_role_arn" {
  value = aws_iam_role.eventbridge.arn
}

output "lambda_role_arn" {
  value = aws_iam_role.lambda.arn
}

output "github_actions_role_arn" {
  value = aws_iam_role.github_actions.arn
}
