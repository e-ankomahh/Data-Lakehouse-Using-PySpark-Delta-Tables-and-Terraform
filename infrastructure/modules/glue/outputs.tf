output "products_job_name" {
  value = aws_glue_job.jobs["products"].name
}

output "orders_job_name" {
  value = aws_glue_job.jobs["orders"].name
}

output "order_items_job_name" {
  value = aws_glue_job.jobs["order_items"].name
}

output "products_crawler_name" {
  value = aws_glue_crawler.products.name
}

output "orders_crawler_name" {
  value = aws_glue_crawler.orders.name
}

output "order_items_crawler_name" {
  value = aws_glue_crawler.order_items.name
}
