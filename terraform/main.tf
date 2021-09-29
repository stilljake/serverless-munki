# NOTE: currently the _only_ supported provider region is us-east-1.
provider "aws" {
  region  = "us-east-1"
}

module "munki-repo" {
  source          = "github.com/grahamgilbert/terraform-aws-munki-repo"
  munki_s3_bucket = var.munki_s3_bucket
  username        = var.username
  password        = var.password
  prefix          = var.prefix
  price_class     = var.price_class
}
