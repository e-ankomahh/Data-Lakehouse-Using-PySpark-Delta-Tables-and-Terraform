provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "lakehouse-ecommerce"
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = "data-engineering"
    }
  }
}
