output "state_machine_arn" {
  value = aws_sfn_state_machine.lakehouse_pipeline.arn
}

output "state_machine_name" {
  value = aws_sfn_state_machine.lakehouse_pipeline.name
}

output "sfn_log_group_name" {
  value = aws_cloudwatch_log_group.sfn_logs.name
}
