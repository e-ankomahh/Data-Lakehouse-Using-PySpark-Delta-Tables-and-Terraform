output "event_rule_name" {
  value = aws_cloudwatch_event_rule.raw_file_arrival.name
}

output "event_rule_arn" {
  value = aws_cloudwatch_event_rule.raw_file_arrival.arn
}
