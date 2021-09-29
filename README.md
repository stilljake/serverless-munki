# Serverless Munki

This repository contains cross platform code to deploy a production ready Munki service, complete with AutoPKG, that runs entirely from within a single GitHub repository and an AWS s3 bucket. No other infrastructure is required. More specifically it contains the following:

- Terraform code to setup a Munki repo in AWS S3.
- Actions workflows to handle AutoPKG runs and related tasks.
- Directories for maintaining Munki items and AutoPKG overrides.


## Deployment

### Initial GitHub Setup

Firstly, you will need to create a new GitHub repository with Actions enabled. You can then clone this repo and copy its contents into your own private repo by running the following Terminal commands:

```bash
git clone git@github.com:adahealth/serverless-munki.git
cd serverless-munki
make init
```

By default this will create a new directory named `my-serverless-munki` inside the parent directory of our cloned repo and initialize it as it's own Git repository. Now we can install (if you haven't already) and configure Git LFS for your repo. In our example, We are installing Git LFS via Homebrew but feel free to install it how ever you like.

```bash
brew install git-lfs
make lfs
```

Then you can go ahead and push your new repo to the Actions enabled GitHub repository you created earlier.

```bash
cd ../my-serverless-munki
git remote add origin <your-github-repo-url>
git branch -M master
git push -u origin master
```

### AWS / Terraform setup

Log in to your AWS account and create an AWS IAM user with the following permissions: `AWSLambdaFullAccess`, `IAMFullAccess`, `AmazonS3FullAccess`, `CloudFrontFullAccess`. Then create an access key for the user and set the access key ID and secret key as environment variables. This is so that Terraform can authenticate to the AWS provider. Also, if you don't have Terraform installed you should do that now too.

```bash
brew install terraform@1.0
export AWS_ACCESS_KEY_ID="<your-access-key-id>"
export AWS_SECRET_ACCESS_KEY="<your-secret-key>"
```

While we're at it, we can also add both the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as [GitHub Actions secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets#creating-encrypted-secrets-for-a-repository) in our remote repo. They will be used in our Actions workflows when syncing our Munki files to our S3 bucket.

Next, we need to set our Terraform variables for our AWS configuration. Open the `/terraform/variables.tf` file and adjust the variables to match what you want the bucket to be called, and set the username and password your Munki clients will use to access the repo.

```terraform
# prefix should be globally unique. Some characters seem to cause issues;
# Something like yourorg_munki might be a good prefix.
variable "prefix" {
  default = "YOU_BETTER_CHANGE_ME"
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
```

Now we can change in to the terraform directory and check our Terraform plan.

```bash
cd terraform
terraform init
terraform plan
```

If everything is as expected we can apply the configuration.

```bash
terraform apply
```

That's it for our Munki "server" repository, We can use terraform outputs to obtain info for your client configuration

```bash
terraform output cloudfront_url 
# This is your SoftwareRepoURL.


terraform output username       
terraform output password  
# These are the credentials that your clients will use to access the S3 bucket
```

### Slack notifications

To configure Slack notifications. Simply create an [incoming webhook](https://slack.com/intl/en-de/help/articles/115005265063-Incoming-webhooks-for-Slack) in your Slack tenant and add the webook URL as a GitHub Actions secret with the name `SLACK_WEBHOOK`

## Usage

### AutoPKG

Add your AutoPKG recipe overrides to the `RecipeOverrides/` folder. Add any necessary parent recipe repos to the `.github/workflows/autopkg-run.yml` workflow file by appending a `repo-add` command to the "Add AutoPkg repos" step.

```yaml
- name: Add AutoPkg repos
        run: | 
          autopkg repo-add recipes
          autopkg repo-add <parent-recipe-repo1>
          autopkg repo-add <parent-recipe-repo2>
          autopkg repo-add <parent-recipe-repo3>
          # etc
```

Every time the autopkg-run workflow is triggered the following steps will happen inside of a GitHub Actions runner VM:

  - Repository is checked out containing AutoPkg overrides and Munki Repo.
  - Munki and AutoPkg installed and configured.
  - Each recipe in the RecipeOverides directory is run.
  - If AutoPKG imported any new items into Munki, Commit the changes and create a PR.
  - If enabled, post results to Slack.

By default this is scheduled to run at 6am everyday between Monday and Friday. You can change this by editing the schedule in `.github/workflows/autopkg-run.yml`.

After reviewing and Merging any PRs created via the autopkg-run workflow, the sync-repo workflow will be triggered. This will sync any changes in your munki repo to your AWS S3 bucket where they will be available for your clients.

### Munki

You can administer your munki repo however you are used to by checking out your GitHub repo locally and making your required changes inside the `munki_repo` folder. When changes are pushed to the remote Master branch, they will be automatically synced to your S3 bucket via the sync-repo workflow.

## Acknowledgements

[Terraform Munki Repo](https://github.com/grahamgilbert/terraform-aws-munki-repo) module from Graham Gilbert

The autopkg_tools.py script is a fork of Facebook's [autopkg_tools.py](https://github.com/facebook/IT-CPE/blob/main/legacy/autopkg_tools/autopkg_tools.py)

The GitHub Actions workflows and this project in general are based heavily on the GitHub Actions AutoPKG setup from [Gusto](https://github.com/Gusto/it-cpe-opensource/tree/main/autopkg)