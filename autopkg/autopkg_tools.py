#!/usr/bin/python3
# Copyright (c) Facebook, Inc. and its affiliates.
# Modifications copyright (C) 2021 Ada Health GmbH

"""Wrapper script for handling AutoPKG operations."""

import os
import json
import requests
import subprocess
import plistlib


WEBHOOK_URL = os.environ['SLACK_WEBHOOK']
GIT = "/usr/bin/git"
GITHUB_CLI = "gh"
REPO_DIR = os.environ['GITHUB_WORKSPACE'] + "/munki_repo"
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
INPUT_RECIPES = os.environ['INPUT_RECIPES'].split()


class Error(Exception):
    """Base class for domain-specific exceptions."""


class GitError(Error):
    """Git exceptions."""


class BranchError(Error):
    """Branch-related exceptions."""


class PushError(Error):
    """Push-related exceptions."""


# Utility functions
def run_cmd(cmd):
    """Run a command and return the output."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    (out, err) = proc.communicate()
    results_dict = {
        'stdout': out,
        'stderr': err,
        'status': proc.returncode,
        'success': proc.returncode == 0
    }
    return results_dict


def run_live(command):
    """Run a command with real-time output"""
    proc = subprocess.run(
        command,
        stderr=subprocess.PIPE,
        text=True
    )
    results_dict = {
        'status': proc.returncode,
        'success': proc.returncode == 0,
        'stderr': proc.stderr
    }
    return results_dict


# Recipe handling
def get_recipes():
    """Create the list of overrides to run"""
    recipes = []
    for root, dirs, files in os.walk("autopkg/RecipeOverrides"):
        for file in files:
            if file.endswith('.recipe'):
                recipes.append(file)
    return recipes


def parse_recipe_name(identifier):
    """Get the name of the recipe."""
    branch = identifier.replace(' ', '-').lower().split('.munki')[0]
    # Check to see if branch name already exists
    current_branches = branch_list()
    if branch in current_branches:
        # If the same name already exists, append a '-2' to it
        branch += '-2'
    return branch


def parse_report_plist(report_plist_path):
    """Parse the report plist path for a dict of the results."""
    imported_items = []
    failed_items = []
    with open(report_plist_path, "rb") as file:
        report_data = plistlib.load(file)
    if report_data['summary_results']:
        # This means something happened
        munki_results = report_data['summary_results'].get(
            'munki_importer_summary_result', {}
        )
        for imported_item in munki_results.get('data_rows', []):
            imported_items.append(imported_item)
    if report_data['failures']:
        # This means something went wrong
        for failed_item in report_data['failures']:
            # For each recipe that failed, file a task
            failed_items.append(failed_item)
    return {
        'imported': imported_items,
        'failed': failed_items
    }


# Git-related functions
def git_run(arglist):
    """Run git with the argument list."""
    # Only run git commands in the munki repo dir
    owd = os.getcwd()
    os.chdir(REPO_DIR)
    gitcmd = [GIT]
    for arg in arglist:
        gitcmd.append(str(arg))
    results = run_cmd(gitcmd)
    os.chdir(owd)
    if not results['success']:
        raise GitError("Git error: %s" % results['stderr'])
    return results['stdout']


def branch_list():
    """Get the list of current git branches."""
    git_args = ['branch']
    branch_output = git_run(git_args).rstrip()
    if branch_output:
        return [x.strip().strip('* ')
                for x in branch_output.decode().split('\n')]
    return []


def current_branch():
    """Return the name of the current git branch."""
    git_args = ['symbolic-ref', '--short', 'HEAD']
    return str(git_run(git_args).strip())


def create_feature_branch(branch):
    """Create new feature branch."""
    if current_branch() != 'master':
        # Switch to master first if we're not already there
        change_feature_branch('master')
    # Now create new branch
    change_feature_branch(branch, new=True)


def change_feature_branch(branch, new=False):
    """Swap to feature branch."""
    gitcmd = ['checkout']
    if new:
        gitcmd.append('-b')
    gitcmd.append(branch)
    try:
        git_run(gitcmd)
    except GitError as e:
        raise BranchError(
            "Couldn't switch to '%s': %s" % (branch, e)
        )


def rename_branch_version(branch, version):
    """Rename a branch to include the version."""
    new_branch_name = branch + "-%s" % version
    if new_branch_name in branch_list():
        print("Branch %s already exists" % new_branch_name)
        new_branch_name += '-2'
    gitcmd = ['branch', '-m', branch, new_branch_name]
    git_run(gitcmd)
    return new_branch_name


def git_push(branch):
    """Perform a git push."""
    print('Running `git push`...')
    gitpushcmd = ['push', '--set-upstream', 'origin']
    gitpushcmd.append(branch)
    try:
        git_run(gitpushcmd)
    except GitError as e:
        print("Failed to push branch %s" % branch)
        return {
            'success': False,
            'error': e,
            'branch': branch
        }
    return {
        'success': True
    }


def pull_request(branchname):
    """Create Pull request using the hub cli tool."""
    if not GITHUB_TOKEN:
        print('Pull request not created.. GITHUB_TOKEN not set')
        return
    print('Creating Pull Request...')
    run_cmd([
      GITHUB_CLI,
      "pr", "create",
      "-B", "main",
      "-H", branchname,
      "-f"
    ])


def create_commit(imported_item):
    """Create git commit."""
    print('Adding items...')
    gitaddcmd = ['add']
    gitaddcmd.append(REPO_DIR)
    git_run(gitaddcmd)
    print('Creating commit...')
    gitcommitcmd = ['commit', '-m']
    message = "Update %s to version %s" % (str(imported_item['name']),
                                           str(imported_item["version"]))
    gitcommitcmd.append(message)
    git_run(gitcommitcmd)


# Slack related functions
def imported_message(imported):
    """Format a list of imported items for a slack message"""
    imported_msg = [{
        "type": "section",
        "text": {
            "type": "plain_text",
            "text": "The following items will be imported "
                    "into munki after approval"
        }
    }]
    for item in imported:
        version = item["version"]
        name = item["branchname"]
        imported_info = [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"• {name} version {version}"
            }
        }]
        imported_msg.extend(imported_info)

    return imported_msg


def failures_message(failed):
    """Format a list of failed recipes for a slack message"""
    failures_msg = [{
        "color": '#f2c744',
        "blocks": [
            {"type": "divider"},
            {"type": "section",
             "text": {
                 "type": "mrkdwn",
                 "text": ":warning: *The following recipes failed*"
             }}
        ]
    }]
    for item in failed:
        info = item["message"]
        name = item["recipe"]
        failure_info = [
            {"type": "section",
             "text": {"type": "mrkdwn", "text": f"{name}"}},
            {"type": "section",
             "text": {"type": "mrkdwn", "text": f"```{info}```"}}
        ]
        failures_msg[0]['blocks'].extend(failure_info)
    return failures_msg


def git_errors_message(git_info):
    """Format a list of any git errors to send as slack message"""
    git_msg = [{
        "color": "#f2c744",
        "blocks": [
            {"type": "divider"},
            {"type": "section",
             "text": {"type": "mrkdwn", "text": ":github: *Git errors*"}},
        ]}
    ]
    for item in git_info:
        name = item['branch']
        info = item['error']
        git_info = [{
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"error pushing branch: {name} ```{info}```"}
        }]
        git_msg[0]['blocks'].extend(git_info)
    return git_msg


def format_slack_message(imported, failed, git_info):
    """Compose notification to be sent to slack"""
    message = {
        "blocks": [],
        "attachments": [{
            "color": "#4bb543",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":package: *AutoPkg has finished running*"
                 }
            }]
        }]
    }
    if not imported:
        msg_info = [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "There are no new items to be imported into Munki"
            }
        }]
        message['attachments'][0]['blocks'].extend(msg_info)
    else:
        message['attachments'][0]['blocks'].extend(imported_message(imported))
    if failed:
        message['attachments'].extend(failures_message(failed))
    if git_info:
        message['attachments'].extend(git_errors_message(git_info))

    return message


def post_to_slack(message):
    """Post slack message to the WEBHOOK_URL"""
    response = requests.post(
                WEBHOOK_URL, data=json.dumps(message),
                headers={'Content-Type': 'application/json'}
                )
    print(f"Post Slack Message: status: {response.status_code}")


# Autopkg execution functions
def autopkg_run(recipe):
    """Run autopkg on given recipe"""
    autopkg_cmd = ["/usr/local/bin/autopkg", "run", "-v"]
    autopkg_cmd.append(recipe)
    autopkg_cmd.append("--report-plist")
    autopkg_cmd.append("report.plist")
    run_live(autopkg_cmd)


def handle_recipes():
    imported = []
    failed = []
    git_errors = []
    if INPUT_RECIPES:
        recipes = INPUT_RECIPES
    else:
        recipes = get_recipes()
    for recipe in recipes:
        # Parse the recipe name for basic item name
        branchname = parse_recipe_name(recipe)
        # Create new branch for item
        create_feature_branch(branchname)
        # Run Autopkg
        autopkg_run(recipe)
        # Parse the results from report plist
        run_results = parse_report_plist("report.plist")
        if not run_results['imported'] and not run_results['failed']:
            # Nothing happened
            continue
        if run_results['failed']:
            # Add to list of failed items
            failed.append(run_results['failed'][0])
        if run_results['imported']:
            # Commit changes
            create_commit(run_results['imported'][0])
            branch_version = rename_branch_version(
                branchname,
                str(run_results['imported'][0]['version'])
            )
            # Push changes to github
            push_result = git_push(branch_version)
            if not push_result['success']:
                # This means there was a problem pushing changes to github
                # Add to list of git errors
                git_errors.append(push_result)
            else:
                # If push was successful then create a PR
                pull_request(branch_version)
                # Add basic item name to imported results so we can tell
                # the difference between arm and intel items
                run_results['imported'][0]['branchname'] = branchname
                # Add to list of imported items
                imported.append(run_results['imported'][0])

    if not WEBHOOK_URL:
        print("Slack Webhook not set.. No notification sent.")
        return

    # Send a report of what happened to slack
    slack_notification = format_slack_message(imported, failed, git_errors)
    post_to_slack(slack_notification)


if __name__ == '__main__':
    handle_recipes()
