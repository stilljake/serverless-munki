# prefix should be globally unique. Some characters seem to cause issues;
# Something like yourorg_munki might be a good prefix.
variable "prefix" {
  default = "you_better_change_me"
}

# you'd need to change this only if you have an existing bucket named
# "munki-s3-bucket"
variable "munki_s3_bucket" {
  default = "munki-s3-bucket"
}

# the price class for your CloudFront distribution
# one of PriceClass_All, PriceClass_200, PriceClass_100
variable "price_class" {
  default = "PriceClass_100"
}

# the username your Munki clients will use for BasicAuthentication
variable "username" {
  default = "YOU_BETTER_CHANGE_ME"
}

# the password your Munki clients will use for BasicAuthentication
variable "password" {
  default = "YOU_BETTER_CHANGE_ME"
}