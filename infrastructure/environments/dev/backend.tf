terraform {
  backend "s3" {
    bucket         = "lakehouse-tfstate-249946084242"
    key            = "lakehouse/dev/terraform.tfstate"
    region         = "eu-west-1"
    encrypt        = true
    dynamodb_table = "lakehouse-tfstate-lock"
  }
}
