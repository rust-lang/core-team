#!/usr/bin/env python3
# Copyright (c) 2020 Pietro Albini <pietro@pietroalbini.org>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import pathlib
import requests
import sys


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent


def can_open_issues(client, repo, username):
    resp = client.get(f"https://api.github.com/repos/{repo}/collaborators/{username}")
    return resp.status_code == 204


def handle_new_issue(client, repo, number):
    resp = client.get(f"https://api.github.com/repos/{repo}/issues/{number}")
    resp.raise_for_status()
    issue = resp.json()

    allowed = can_open_issues(client, repo, issue["user"]["login"])

    # Leave a comment explaining what's happening.
    if allowed:
        comment_body = (SCRIPT_DIR / "message-valid.md").open().read()
    else:
        comment_body = (SCRIPT_DIR / "message-invalid.md").open().read()
    resp = client.post(f"https://api.github.com/repos/{repo}/issues/{number}/comments", json={
        "body": comment_body,
    })
    resp.raise_for_status()

    # Close the issue.
    if not allowed:
        resp = client.patch(f"https://api.github.com/repos/{repo}/issues/{number}", json={
            "state": "closed",
        })
        resp.raise_for_status()

    # Always lock the issues.
    resp = client.put(f"https://api.github.com/repos/{repo}/issues/{number}/lock")
    resp.raise_for_status()

    # Prevent the next GitHub Actions steps from running
    if not allowed:
        exit(1)


if __name__ == "__main__":
    github_token = os.environ["GITHUB_TOKEN"]
    repo = sys.argv[1]
    issue_number = int(sys.argv[2])

    client = requests.Session()
    client.headers.update({
        "Authorization": f"token {github_token}",
        "User-Agent": "https://github.com/rust-lang/core-team automation",
    })

    handle_new_issue(client, repo, issue_number)
