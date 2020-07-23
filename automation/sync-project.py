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

# This script automatically synchronizes issues in a GitHub repository with an
# organization's project board. To configure synchronization, add a note to the
# column you want to sync with the following content:
#
#   **automation**
#   repo: REPOSITORY_NAME
#   label: LABEL_NAME
#

import json
import os
import requests
import sys


# Fetch all the contents of an organization board
BOARD_QUERY = """
query($org: String!, $project: Int!) {
  organization(login: $org) {
    project(number: $project) {
      columns(first: 100) {
        nodes {
          databaseId
          cards(first: 100, archivedStates: NOT_ARCHIVED) {
            nodes {
              databaseId
              note
              content {
                ... on Issue {
                  number
} } } } } } } } }
"""


class Column:
    def __init__(self, id):
        self.id = id
        self.notes = []
        self.issues = []

    def automated_label(self, repo):
        for note in self.notes:
            lines = note.text.split('\n')
            if not lines or lines[0].strip() != "**automation**":
                continue

            try:
                kv = {}
                for line in lines[1:]:
                    key, value = line.split(':', 1)
                    kv[key.strip()] = value.strip()
                if kv["repo"] == repo:
                    return kv["label"]
            except (KeyError, ValueError):
                continue


class NoteCard:
    def __init__(self, card_id, text):
        self.card_id = card_id
        self.text = text


class IssueCard:
    def __init__(self, card_id, issue_id):
        self.card_id = card_id
        self.issue_id = issue_id


class Issue:
    def __init__(self, id, number):
        self.id = id
        self.number = number


def fetch_project(client, org, project):
    query = client.post("https://api.github.com/graphql", data=json.dumps({
        "query": BOARD_QUERY,
        "variables": {
            "org": org,
            "project": project,
        },
    })).json()

    columns = []
    for raw_column in query["data"]["organization"]["project"]["columns"]["nodes"]:
        column = Column(raw_column["databaseId"])
        for card in raw_column["cards"]["nodes"]:
            if card["note"] is not None:
                column.notes.append(NoteCard(card["databaseId"], card["note"]))
            if card["content"] is not None:
                column.issues.append(IssueCard(card["databaseId"], card["content"]["number"]))
        columns.append(column)

    return columns


def fetch_issues(client, org, repo, label):
    response = client.get(
        f"https://api.github.com/repos/{org}/{repo}/issues?labels={label}&state=open&per_page=100"
    ).json()

    issues = []
    for issue in response:
        issues.append(Issue(issue["id"], issue["number"]))
    return issues


def create_issue_card(client, column_id, issue_id):
    response = client.post(f"https://api.github.com/projects/columns/{column_id}/cards", data=json.dumps({
        "content_id": issue_id,
        "content_type": "Issue",
    }), headers={
        "Accept": "application/vnd.github.inertia-preview+json"
    })
    assert response.status_code == 201


def remove_card(client, card_id):
    response = client.delete(f"https://api.github.com/projects/columns/cards/{card_id}", headers={
        "Accept": "application/vnd.github.inertia-preview+json"
    })
    assert response.status_code == 204


def synchronize(client, org, project, current_repo):
    columns = fetch_project(client, org, project)
    for column in columns:
        label = column.automated_label(current_repo)
        if label is None:
            continue

        current_issues = {card.issue_id: card.card_id for card in column.issues}
        issues = fetch_issues(client, org, current_repo, label)

        for issue in issues:
            if issue.number in current_issues:
                del current_issues[issue.number]
            else:
                print(f"adding issue {issue.number} to the board")
                create_issue_card(client, column.id, issue.id)
        for issue_number, card_id in current_issues.items():
            print(f"removing issue {issue_number} from the board")
            remove_card(client, card_id)


if __name__ == "__main__":
    token = os.environ["GITHUB_TOKEN"]
    org = sys.argv[1]
    project = int(sys.argv[2])
    repo = sys.argv[3]

    client = requests.Session()
    client.headers.update({
        "Authorization": f"token {token}"
    })

    synchronize(client, org, project, repo)
