import demistomock as demisto
from CommonServerPython import *
from CommonServerUserPython import *

''' IMPORTS '''

import json
import requests
from typing import Union
from datetime import datetime

# Disable insecure warnings
requests.packages.urllib3.disable_warnings()

''' GLOBALS/PARAMS '''

USER = demisto.params().get('user')
TOKEN = demisto.params().get('token', '')
BASE_URL = 'https://api.github.com'
REPOSITORY = demisto.params().get('repository')
CONTRIBUTION_LABEL = demisto.params().get('contribution_label')
BOT_NAME = demisto.params().get('bot_name')
STALE_TIME = demisto.params().get('stale_time', '3 days')
USE_SSL = not demisto.params().get('insecure', False)
FETCH_TIME = demisto.params().get('fetch_time', '30 days')

USER_SUFFIX = '/repos/{}/{}'.format(USER, REPOSITORY)
ISSUE_SUFFIX = USER_SUFFIX + '/issues'
RELEASE_SUFFIX = USER_SUFFIX + '/releases'
PULLS_SUFFIX = USER_SUFFIX + '/pulls'

RELEASE_HEADERS = ['ID', 'Name', 'Download_count', 'Body', 'Created_at', 'Published_at']
ISSUE_HEADERS = ['ID', 'Repository', 'Title', 'State', 'Body', 'Created_at', 'Updated_at', 'Closed_at', 'Closed_by',
                 'Assignees', 'Labels']

# Headers to be sent in requests
HEADERS = {
    'Authorization': "Bearer " + TOKEN
}

# REVIEWERS = ['Itay4', 'yaakovi', 'yuvalbenshalom', 'ronykoz']
REVIEWERS = ['avidan-H']
CONTENT_TEAM_ID = 3043448

WELCOME_MSG = 'Thank you for your contribution. Your generosity and caring are unrivaled! Rest assured - our content ' \
              'wizard @reviewer will very shortly look over your proposed changes.'
NEEDS_REVIEW_MSG = '@reviewer This PR won\'t review itself and I\'m not going to do it for you (I bet you\'d like ' \
                   'that wouldn\'t you) - look it over, eh?'
LOTR_NUDGE_MSG = '"And some things that should not have been forgotten were lost. History became legend. Legend ' \
                 'became myth. And for two and a half thousand years..." @reviewer had not looked at this ' \
                 'beautiful PR - as they were meant to do.'
NUDGE_AUTHOR_MSG = 'A lengthy period of time has transpired since the PR was reviewed. @author Please address the ' \
                   'reviewer\'s comments and push your committed changes.'
APPROVED_UNMERGED_MSG = 'The PR was approved but doesn\'t seem to have been merged. @author Please verify that there ' \
                        'aren\'t any outstanding requested changes.'
SUGGEST_CLOSE_MSG = 'These reminders don\'t seem to be working and the issue is getting pretty stale - @reviewer - ' \
                    'consider whether this PR is still relevant or should be closed.'
STALE_MSG = 'This PR is starting to get a little stale and possibly even a little moldy and smelly.'
UNIT_TEST_MSG = ' It is very likely that the reviewer will want you to add a unittest for your '\
        'code changes in the `$unittest$` file - please refer to the documentation '\
        'https://github.com/demisto/content/tree/master/docs/tests/unit-testing for more details.'
CHANGELOG_MSG = ' Because of your changes you will also need to update the `$changelog$` file - please refer '\
        'to the documentation https://github.com/demisto/content/tree/master/docs/release_notes for more details.'

''' HELPER FUNCTIONS '''


def http_request(method, url_suffix, params=None, data=None):
    res = requests.request(
        method,
        BASE_URL + url_suffix,
        verify=USE_SSL,
        params=params,
        data=json.dumps(data),
        headers=HEADERS
    )
    if res.status_code >= 400:
        try:
            json_res = res.json()

            if json_res.get('errors') is None:
                return_error('Error in API call to the GitHub Integration [%d] - %s' % (res.status_code, res.reason))

            else:
                error_code = json_res.get('errors')[0].get('code')
                if error_code == 'missing_field':
                    return_error(
                        'Error: the field: "{}" requires a value'.format(json_res.get('errors')[0].get('field')))

                elif error_code == 'invalid':
                    field = json_res.get('errors')[0].get('field')
                    if field == 'q':
                        return_error('Error: invalid query - {}'.format(json_res.get('errors')[0].get('message')))

                    else:
                        return_error('Error: the field: "{}" has an invalid value'.format(field))

                elif error_code == 'missing':
                    return_error('Error: {} does not exist'.format(json_res.get('errors')[0].get('resource')))

                elif error_code == 'already_exists':
                    return_error('Error: the field {} must be unique'.format(json_res.get('errors')[0].get('field')))

                else:
                    return_error(
                        'Error in API call to the GitHub Integration [%d] - %s' % (res.status_code, res.reason))

        except ValueError:
            return_error('Error in API call to GitHub Integration [%d] - %s' % (res.status_code, res.reason))

    try:
        return res.json()

    except Exception as excep:
        return_error('Error in HTTP request - {}'.format(str(excep)))


def data_formatting(title, body, labels, assignees, state):
    """This method creates a dictionary to be used as "data" field in an http request."""
    data = {}
    if title is not None:
        data['title'] = title

    if body is not None:
        data['body'] = body

    if state is not None:
        data['state'] = state

    if labels is not None:
        data['labels'] = labels.split(',')

    if assignees is not None:
        data['assignees'] = assignees.split(',')

    return data


def context_create_issue(response, issue):
    """ Create GitHub.Issue EntryContext and results to be printed in Demisto.

    Args:
        response (dict): The raw HTTP response to be inserted to the 'Contents' field.
        issue (dict or list): A dictionary or a list of dictionaries formatted for Demisto results.
    """
    ec = {
        'GitHub.Issue(val.Repository == obj.Repository && val.ID == obj.ID)': issue
    }
    return_outputs(tableToMarkdown("Issues:", issue, headers=ISSUE_HEADERS, removeNull=True), ec, response)


def list_create(issue, list_name, element_name):
    """ Creates a list if parameters exist in issue.

    Args:
        issue(dict): an issue from GitHub.
        list_name (str): the name of the list in the issue.
        element_name (str): the field name of the element in the list.

    Returns:
        The created list or None if it does not exist.
    """
    if issue.get(list_name) is not None:
        return [element.get(element_name) for element in issue.get(list_name)]

    else:
        None


def issue_format(issue):
    """ Create a dictionary with selected fields representing an issue in Demisto.

    Args:
        issue (dict): An HTTP response representing an issue, formatted as a dictionary

    Returns:
        (dict). representing an issue in Demisto.
    """
    closed_by = None
    if issue.get('closed_by') is not None and issue.get('state') == 'closed':
        closed_by = issue.get('closed_by').get('login')

    form = {
        'ID': issue.get('number'),
        'Repository': REPOSITORY,
        'Title': issue.get('title'),
        'Body': issue.get('body'),
        'State': issue.get('state'),
        'Labels': list_create(issue, 'labels', 'name'),
        'Assignees': list_create(issue, 'assignees', 'login'),
        'Created_at': issue.get('created_at'),
        'Updated_at': issue.get('updated_at'),
        'Closed_at': issue.get('closed_at'),
        'Closed_by': closed_by
    }
    return form


def create_issue_table(issue_list, response, limit):
    """ Get an HTTP response and a list containing several issues, sends each issue to be reformatted.

    Args:
        issue_list(list): derived from the HTTP response
        response (dict):A raw HTTP response sent for 'Contents' field in context

    Returns:
        The issues are sent to Demisto as a list.
    """
    issue_list.reverse()
    issue_table = []
    issue_count = 0
    for issue in issue_list:
        issue_table.append(issue_format(issue))
        issue_count = issue_count + 1
        if issue_count == limit:
            break

    context_create_issue(response, issue_table)


def format_commit_outputs(commit: dict) -> dict:
    """Take GitHub API commit data and format to expected context outputs

    Args:
        commit (dict): commit data returned from GitHub API

    Returns:
        (dict): commit object formatted to expected context outputs
    """
    author = commit.get('author', {})
    ec_author = {
        'Date': author.get('date'),
        'Name': author.get('name'),
        'Email': author.get('email')
    }
    committer = commit.get('committer', {})
    ec_committer = {
        'Date': committer.get('date'),
        'Name': committer.get('name'),
        'Email': committer.get('email')
    }
    parents = commit.get('parents', [])
    formatted_parents = [{'SHA': parent.get('sha')} for parent in parents]

    verification = commit.get('verification', {})
    ec_verification = {
        'Verified': verification.get('verified'),
        'Reason': verification.get('reason'),
        'Signature': verification.get('signature'),
        'Payload': verification.get('payload')
    }

    ec_object = {
        'SHA': commit.get('sha'),
        'Author': ec_author,
        'Committer': ec_committer,
        'Message': commit.get('message'),
        'Parent': formatted_parents,
        'TreeSHA': commit.get('tree', {}).get('sha'),
        'Verification': ec_verification
    }
    return ec_object


def format_label_outputs(label: dict) -> dict:
    """Take GitHub API label data and format to expected context outputs

    Args:
        label (dict): label data returned from GitHub API

    Returns:
        (dict): label object formatted to expected context outputs
    """
    ec_object = {
        'ID': label.get('id'),
        'NodeID': label.get('node_id'),
        'Name': label.get('name'),
        'Description': label.get('description'),
        'Color': label.get('Color'),
        'Default': label.get('default')
    }
    return ec_object


def format_user_outputs(user: dict) -> dict:
    """Take GitHub API user data and format to expected context outputs

    Args:
        user (dict): user data returned from GitHub API

    Returns:
        (dict): user object formatted to expected context outputs
    """
    ec_user = {
        'Login': user.get('login'),
        'ID': user.get('id'),
        'NodeID': user.get('node_id'),
        'Type': user.get('type'),
        'SiteAdmin': user.get('site_admin')
    }
    return ec_user


def format_head_or_base_outputs(head_or_base: dict) -> dict:
    """Take GitHub API head or base branch data and format to expected context outputs

    Args:
        head_or_base (dict): head or base branch data returned from GitHub API

    Returns:
        (dict): head or base branch object formatted to expected context outputs
    """
    head_or_base_user = head_or_base.get('user', {})
    ec_head_or_base_user = format_user_outputs(head_or_base_user)
    head_or_base_repo = head_or_base.get('repo', {})
    head_or_base_repo_owner = head_or_base_repo.get('owner', {})
    ec_head_or_base_repo_owner = format_user_outputs(head_or_base_repo_owner)
    ec_head_repo = {
        'ID': head_or_base_repo.get('id'),
        'NodeID': head_or_base_repo.get('node_id'),
        'Name': head_or_base_repo.get('name'),
        'FullName': head_or_base_repo.get('full_name'),
        'Owner': ec_head_or_base_repo_owner,
        'Private': head_or_base_repo.get('private'),
        'Description': head_or_base_repo.get('description'),
        'Fork': head_or_base_repo.get('fork'),
        'Language': head_or_base_repo.get('language'),
        'ForksCount': head_or_base_repo.get('forks_count'),
        'StargazersCount': head_or_base_repo.get('stargazers_count'),
        'WatchersCount': head_or_base_repo.get('watchers_count'),
        'Size': head_or_base_repo.get('size'),
        'DefaultBranch': head_or_base_repo.get('default_branch'),
        'OpenIssuesCount': head_or_base_repo.get('open_issues_count'),
        'Topics': head_or_base_repo.get('topics'),
        'HasIssues': head_or_base_repo.get('has_issues'),
        'HasProjects': head_or_base_repo.get('has_projects'),
        'HasWiki': head_or_base_repo.get('has_wiki'),
        'HasPages': head_or_base_repo.get('has_pages'),
        'HasDownloads': head_or_base_repo.get('has_downloads'),
        'Archived': head_or_base_repo.get('archived'),
        'Disabled': head_or_base_repo.get('disabled'),
        'PushedAt': head_or_base_repo.get('pushed_at'),
        'CreatedAt': head_or_base_repo.get('created_at'),
        'UpdatedAt': head_or_base_repo.get('updated_at'),
        'AllowRebaseMerge': head_or_base_repo.get('allow_rebase_merge'),
        'AllowSquashMerge': head_or_base_repo.get('allow_squash_merge'),
        'AllowMergeCommit': head_or_base_repo.get('allow_merge_commit'),
        'SucscribersCount': head_or_base_repo.get('subscribers_count')
    }
    ec_head_or_base = {
        'Label': head_or_base.get('label'),
        'Ref': head_or_base.get('ref'),
        'SHA': head_or_base.get('sha'),
        'User': ec_head_or_base_user,
        'Repo': ec_head_repo,
    }
    return ec_head_or_base


def format_pr_outputs(pull_request: dict) -> dict:
    """Take GitHub API Pull Request data and format to expected context outputs

    Args:
        pull_request (dict): Pull Request data returned from GitHub API

    Returns:
        (dict): Pull Request object formatted to expected context outputs
    """
    user_data = pull_request.get('user', {})
    ec_user = format_user_outputs(user_data)

    labels_data = pull_request.get('labels', [])
    ec_labels = [format_label_outputs(label) for label in labels_data]

    milestone_data = pull_request.get('milestone', {})
    creator = milestone_data.get('creator', {})
    ec_creator = format_user_outputs(creator)
    ec_milestone = {
        'ID': milestone_data.get('id'),
        'NodeID': milestone_data.get('node_id'),
        'Number': milestone_data.get('number'),
        'State': milestone_data.get('state'),
        'Title': milestone_data.get('title'),
        'Description': milestone_data.get('description'),
        'Creator': ec_creator,
        'OpenIssues': milestone_data.get('open_issues'),
        'ClosedIssues': milestone_data.get('closed_issues'),
        'CreatedAt': milestone_data.get('created_at'),
        'UpdatedAt': milestone_data.get('updated_at'),
        'ClosedAt': milestone_data.get('closed_at'),
        'DueOn': milestone_data.get('due_on'),
    }

    assignees_data = pull_request.get('assignees', [])
    ec_assignee = [format_user_outputs(assignee) for assignee in assignees_data]

    requested_reviewers_data = pull_request.get('requested_reviewers', [])
    ec_requested_reviewer = [format_user_outputs(requested_reviewer) for requested_reviewer in requested_reviewers_data]

    requested_teams_data = pull_request.get('requested_teams', [])
    ec_requested_team = [
        {
            'ID': requested_team.get('id'),
            'NodeID': requested_team.get('node_id'),
            'Name': requested_team.get('name'),
            'Slug': requested_team.get('slug'),
            'Description': requested_team.get('description'),
            'Privacy': requested_team.get('privacy'),
            'Permission': requested_team.get('permission'),
            'Parent': requested_team.get('parent')
        }
        for requested_team in requested_teams_data
    ]

    head_data = pull_request.get('head', {})
    ec_head = format_head_or_base_outputs(head_data)

    base_data = pull_request.get('base', {})
    ec_base = format_head_or_base_outputs(base_data)

    merged_by_data = pull_request.get('merged_by', {})
    ec_merged_by = format_user_outputs(merged_by_data)

    ec_object = {
        'ID': pull_request.get('id'),
        'NodeID': pull_request.get('node_id'),
        'Number': pull_request.get('number'),
        'State': pull_request.get('state'),
        'Locked': pull_request.get('locked'),
        'User': ec_user,
        'Body': pull_request.get('body'),
        'Label': ec_labels,
        'Milestone': ec_milestone,
        'ActiveLockReason': pull_request.get('active_lock_reason'),
        'CreatedAt': pull_request.get('created_at'),
        'UpdatedAt': pull_request.get('updated_at'),
        'ClosedAt': pull_request.get('closed_at'),
        'MergedAt': pull_request.get('merged_at'),
        'MergeCommitSHA': pull_request.get('merge_commit_sha'),
        'Assignee': ec_assignee,
        'RequestedReviewer': ec_requested_reviewer,
        'RequestedTeam': ec_requested_team,
        'Head': ec_head,
        'Base': ec_base,
        'AuthorAssociation': pull_request.get('author_association'),
        'Draft': pull_request.get('draft'),
        'Merged': pull_request.get('merged'),
        'Mergeable': pull_request.get('mergeable'),
        'Rebaseable': pull_request.get('rebaseable'),
        'MergeableState': pull_request.get('mergeable_state'),
        'MergedBy': ec_merged_by,
        'Comments': pull_request.get('comments'),
        'ReviewComments': pull_request.get('review_comments'),
        'MaintainerCanModify': pull_request.get('maintainer_can_modify'),
        'Commits': pull_request.get('commits'),
        'Additions': pull_request.get('additions'),
        'Deletions': pull_request.get('deletions'),
        'ChangedFiles': pull_request.get('changed_files')
    }
    return ec_object


def format_comment_outputs(comment: dict) -> dict:
    """Take GitHub API Comment data and format to expected context outputs

    Args:
        comment (dict): Comment data returned from GitHub API

    Returns:
        (dict): Comment object formatted to expected context outputs
    """
    ec_object = {
        'ID': comment.get('id'),
        'NodeID': comment.get('node_id'),
        'Body': comment.get('body'),
        'CommenterLogin': comment.get('user', {}).get('login'),
        'CommenterType': comment.get('user', {}).get('type'),
        'CreatedAt': comment.get('created_at'),
        'UpdatedAt': comment.get('updated_at')
    }
    return ec_object


def get_last_event(commit_timestamp: str = '', comment_timestamp: str = '', review_timestamp: str = '') -> str:
    """ Compare dates to determine the last event.

    :param commit_timestamp: timestamp of last pr commit
    :param comment_timestamp: timestamp of last pr comment
    :param review_timestamp:  timestamp of the last pr review
    :return: The last event to occur
    """
    time_fmt = '%Y-%m-%dT%H:%M:%SZ'
    commit_date = datetime.strptime(commit_timestamp, time_fmt) if commit_timestamp else datetime.fromordinal(1)
    comment_date = datetime.strptime(comment_timestamp, time_fmt) if comment_timestamp else datetime.fromordinal(1)
    review_date = datetime.strptime(review_timestamp, time_fmt) if review_timestamp else datetime.fromordinal(1)

    last_event = 'comment' if comment_date >= commit_date else 'commit'
    if last_event == 'comment' and review_date > comment_date:
        last_event = 'review'
    elif last_event == 'commit' and review_date > commit_date:
        last_event = 'review'
    return last_event


def alert_appropriate_party(pr: dict, commit_data: dict, reviews_data: list, comments_data: list):
    requested_reviewers = [requested_reviewer.get('login') for requested_reviewer in pr.get('requested_reviewers', [])]
    reviewers_with_prefix = ' '.join(['@' + reviewer for reviewer in requested_reviewers])

    head_author = pr.get('head', {}).get('user', {}).get('login')
    # commit_author = commit_data.get('author', {}).get('login')
    commit_time = commit_data.get('author', {}).get('date', '')

    demisto.info('REVIEWS: ' + json.dumps(reviews_data, indent=4))
    last_review = reviews_data[-1] if len(reviews_data) >= 1 else {}
    review_time = last_review.get('submitted_at', '')
    review_status = last_review.get('state', '')

    comments = [
        comment for comment in comments_data if not
        (comment.get('body', '').startswith(('Thank', 'Hey')) and comment.get('user', {}).get('login', '') == BOT_NAME)
    ]
    last_comment = comments[-1] if len(comments) >= 1 else {}
    comment_time = last_comment.get('updated_at', '')
    comment_body = last_comment.get('body', '')
    commenter = last_comment.get('user', {}).get('login')

    demisto.info('-----------------------------------')
    demisto.info('commit_time: ' + commit_time + ' comment_time: ' + comment_time + ' review_time: ' + review_time)
    demisto.info('last_comment: ' + json.dumps(last_comment, indent=4))
    demisto.info(f'commenter: {commenter}')
    demisto.info(f'head_author: {head_author}')

    msg = ''
    issue_number = pr.get('number')
    last_event = get_last_event(commit_time, comment_time, review_time)
    if last_event == 'commit':
        msg = NEEDS_REVIEW_MSG.replace('@reviewer', reviewers_with_prefix)
    elif last_event == 'review':
        if review_status != 'APPROVED':
            msg = NUDGE_AUTHOR_MSG.replace('author', head_author)
        else:
            msg = APPROVED_UNMERGED_MSG.replace('author', head_author)
    else:  # last_event == 'comment'
        # Actions if the last comment was by the bot itself
        if commenter == BOT_NAME:
            lotr_nudge = LOTR_NUDGE_MSG.replace('@reviewer', reviewers_with_prefix)
            suggest_close = SUGGEST_CLOSE_MSG.replace('@reviewer', reviewers_with_prefix)
            if review_status in ['PENDING', ''] and (comment_body != lotr_nudge and comment_body != suggest_close):
                msg = lotr_nudge
            elif comment_body == suggest_close:
                # PR already has comment from our bot to consider closing the issue so skip commenting
                return
            else:
                msg = suggest_close
        # Determine who the last commenter was - assume that whichever party was not the commenter needs a reminder
        elif commenter != head_author:
            # The last comment wasn't made by the PR opener (and is probably one of the requested reviewers) assume
            # that the PR opener needs a nudge
            nudge_author = f' @{head_author} are there any changes you wanted to make since @{commenter}\'s last ' \
                f'comment? '
            msg = STALE_MSG + nudge_author
        else:
            # Else assume the person who opened the PR is waiting on the response of one of the reviewers
            nudge_reviewer = ' ' + reviewers_with_prefix + f' what\'s new since @{commenter}\'s last comment?'
            msg = STALE_MSG + nudge_reviewer
    create_comment(issue_number, msg)


def check_pr_files(pull_number, pull_author):
    pr_files = list_pr_files(pull_number)
    filenames = [fileobject.get('filename') for fileobject in pr_files]
    filenames_str = '\n'.join(filenames)
    demisto.info('**********************')
    demisto.info('filenames: ' + json.dumps(filenames, indent=4))
    # accepted_path_prefixes = ['content/Integrations/', 'content/Scripts/']
    py_yml_reg = r"(Integrations|Scripts)/(.*)/(\2\.(?:py|yml))"
    modified_files = re.findall(py_yml_reg, filenames_str)
    demisto.info('######################')
    demisto.info('modified_files: ' + json.dumps(modified_files, indent=4))
    requires = {}
    if modified_files:
        warning = f'Hey @{pull_author}, it appears you made changes ' \
                  f'to {" and ".join(["/".join(mod) for mod in modified_files])}.'
        for modded in modified_files:
            path_prefix, dir_name, file = [modded[0], modded[1], modded[2]]
            test_file = path_prefix + '/' + dir_name + '/' + dir_name + '_test.py'
            changelog_file = path_prefix + '/' + dir_name + '/' + 'CHANGELOG.md'
            if file.endswith('.py') and test_file not in filenames:
                requires['unittest'] = test_file
            if changelog_file not in filenames:
                requires['changelog'] = changelog_file
        if not requires:
            return
        else:
            unit_test = requires.get('unittest')
            changelog = requires.get('changelog')
            warning += UNIT_TEST_MSG.replace('$unittest$', unit_test) if unit_test else ''
            warning += CHANGELOG_MSG.replace('$changelog$', changelog) if changelog else ''
            create_comment(pull_number, warning)


''' REQUESTS FUNCTIONS '''


def get_branch(branch: str) -> dict:
    suffix = USER_SUFFIX + f'/branches/{branch}'
    response = http_request('GET', url_suffix=suffix)
    return response


def create_branch(name: str, sha: str) -> dict:
    suffix = USER_SUFFIX + '/git/refs'
    data = {
        'ref': f'ref/heads/{name}',
        'sha': sha
    }
    response = http_request('POST', url_suffix=suffix, data=data)
    return response


def get_team_membership(team_id: int, user_name: str) -> dict:
    suffix = f'/teams/{team_id}/memberships/{user_name}'
    response = http_request('GET', url_suffix=suffix)
    return response


def request_review(pull_number: int, reviewers: list) -> dict:
    """Make an API call to GitHub to request reviews from a list of users for a given PR

    Args:
        pull_number (int): The number of the PR for which the review request(s) is/are being made
        reviewers (list): The list of GitHub usernames from which you wish to request a review

    Returns:
        dict: API response

    Raises:
        Exception: An exception will be raised if one or more of the requested reviewers is not
            a collaborator of the repo and therefore the API call returns a 'Status: 422 Unprocessable Entity'
    """
    suffix = PULLS_SUFFIX + f'/{pull_number}/requested_reviewers'
    response = http_request('POST', url_suffix=suffix, data={'reviewers': reviewers})
    return response


def create_comment(issue_number, msg: str) -> dict:
    suffix = ISSUE_SUFFIX + f'/{issue_number}/comments'
    response = http_request('POST', url_suffix=suffix, data={'body': msg})
    return response


def list_issue_comments(issue_number: int) -> list:
    suffix = ISSUE_SUFFIX + f'/{issue_number}/comments'
    response = http_request('GET', url_suffix=suffix)
    return response


def list_pr_files(pull_number: int) -> list:
    suffix = PULLS_SUFFIX + f'/{pull_number}/files'
    response = http_request('GET', url_suffix=suffix)
    return response


def list_pr_reviews(pull_number: int) -> list:
    suffix = PULLS_SUFFIX + f'/{pull_number}/reviews'
    response = http_request('GET', url_suffix=suffix)
    return response


def get_commit(commit_sha: str) -> dict:
    suffix = USER_SUFFIX + f'/git/commits/{commit_sha}'
    response = http_request('GET', url_suffix=suffix)
    return response


def add_label(issue_number, labels: list):
    suffix = ISSUE_SUFFIX + f'/{issue_number}'
    response = http_request('POST', url_suffix=suffix, data={'labels': labels})
    return response


def get_pull_request(pull_number):
    suffix = PULLS_SUFFIX + f'/{pull_number}'
    response = http_request('GET', url_suffix=suffix)
    return response


def create_issue(title, body, labels, assignees):
    data = data_formatting(title=title,
                           body=body,
                           labels=labels,
                           assignees=assignees,
                           state=None)

    response = http_request(method='POST',
                            url_suffix=ISSUE_SUFFIX,
                            data=data)
    return response


def close_issue(id):
    response = http_request(method='PATCH',
                            url_suffix=ISSUE_SUFFIX + '/{}'.format(str(id)),
                            data={'state': 'closed'})
    return response


def update_issue(id, title, body, state, labels, assign):
    data = data_formatting(title=title,
                           body=body,
                           labels=labels,
                           assignees=assign,
                           state=state)

    response = http_request(method='PATCH',
                            url_suffix=ISSUE_SUFFIX + '/{}'.format(str(id)),
                            data=data)
    return response


def list_all_issue(state):
    params = {'state': state}
    response = http_request(method='GET',
                            url_suffix=ISSUE_SUFFIX,
                            params=params)
    return response


def search_issue(query):
    response = http_request(method='GET',
                            url_suffix='/search/issues',
                            params={'q': query})
    return response


def get_download_count():
    response = http_request(method='GET',
                            url_suffix=RELEASE_SUFFIX)

    count_per_release = []
    for release in response:
        total_download_count = 0
        for asset in release.get('assets', []):
            total_download_count = total_download_count + asset['download_count']

        release_info = {
            'ID': release.get('id'),
            'Download_count': total_download_count,
            'Name': release.get('name'),
            'Body': release.get('body'),
            'Created_at': release.get('created_at'),
            'Published_at': release.get('published_at')
        }
        count_per_release.append(release_info)

    ec = {
        'GitHub.Release( val.ID == obj.ID )': count_per_release
    }
    return_outputs(tableToMarkdown('Releases:', count_per_release, headers=RELEASE_HEADERS, removeNull=True), ec,
                   response)


def get_relevant_prs(time_or_period: Union[str, datetime], label: str, query: str) -> list:
    reg = re.compile("\.\d{6}$")
    try:
        now = datetime.now()
        # try to parse 'time_or_period' into a starting datetime object
        time_range_start, _ = parse_date_range(time_or_period)
        start_delta = now - time_range_start
        start_time = now - start_delta
        time_or_period = start_time
    except Exception:
        # if parse_date_range threw an exception it means that 'time_or_period' was already in the right format
        pass
    timestamp, _ = reg.subn('', time_or_period.isoformat())
    query = query.replace('{USER}', USER).replace('{REPOSITORY}', REPOSITORY).replace('{timestamp}', timestamp)

    # if label was passed then use it in the query otherwise remove that part of the query
    if label:
        query = query.replace('{label}', label)
    elif ' label:{label}' in query:
        query = query.replace(' label:{label}', '')
    elif ' -label:{label}' in query:
        query = query.replace(' -label:{label}', '')

    matching_issues = search_issue(query).get('items', [])
    relevant_prs = [get_pull_request(issue.get('number')) for issue in matching_issues]
    return relevant_prs


def get_stale_prs(args={}):
    stale_time = args.get('stale_time')
    label = args.get('label')
    query = 'repo:{USER}/{REPOSITORY} is:open updated:<{timestamp} is:pr label:{label}'
    return get_relevant_prs(stale_time, label, query)


''' COMMANDS '''


def test_module():
    http_request(method='GET', url_suffix=ISSUE_SUFFIX, params={'state': 'all'})
    demisto.results("ok")


def get_pull_request_command():
    args = demisto.args()
    pull_number = args.get('pull_number')
    response = get_pull_request(pull_number)

    ec_object = format_pr_outputs(response)
    ec = {
        'GitHub.PR(val.Number === obj.Number)': ec_object
    }
    human_readable = tableToMarkdown(f'Pull Request #{pull_number}', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def add_label_command():
    args = demisto.args()
    issue_number = args.get('issue_number')
    labels = argToList(args.get('labels'))
    response = add_label(issue_number, labels)

    ec_object = [format_label_outputs(label) for label in response]
    ec = {
        'GitHub.Label(val.ID === obj.ID)': ec_object
    }
    human_readable = tableToMarkdown('Added Labels', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def get_commit_command():
    args = demisto.args()
    commit_sha = args.get('commit_sha')
    response = get_commit(commit_sha)

    ec_object = format_commit_outputs(response)
    ec = {
        'GitHub.Commit(val.SHA === obj.SHA)': ec_object
    }
    human_readable = tableToMarkdown('Commit', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def list_pr_reviews_command():
    args = demisto.args()
    pull_number = args.get('pull_number')
    response = list_pr_reviews(pull_number)

    formatted_pr_reviews = [
        {
            'ID': pr_review.get('id'),
            'NodeID': pr_review.get('node_id'),
            'Body': pr_review.get('body'),
            'CommitID': pr_review.get('commit_id'),
            'State': pr_review.get('state'),
            'User': format_user_outputs(pr_review.get('user', {}))
        }
        for pr_review in response
    ]
    ec_object = {
        'Number': pull_number,
        'Review': formatted_pr_reviews
    }
    ec = {
        'GitHub.PR(val.Number === obj.Number)': ec_object
    }
    human_readable = tableToMarkdown('Pull Request Files', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def list_pr_files_command():
    args = demisto.args()
    pull_number = args.get('pull_number')
    response = list_pr_files(pull_number)

    formatted_pr_files = [
        {
            'SHA': pr_file.get('sha'),
            'Name': pr_file.get('filename'),
            'Status': pr_file.get('status'),
            'Additions': pr_file.get('additions'),
            'Deletions': pr_file.get('deletions'),
            'Changes': pr_file.get('changes')
        }
        for pr_file in response
    ]
    ec_object = {
        'Number': pull_number,
        'File': formatted_pr_files
    }
    ec = {
        'GitHub.PR(val.Number === obj.Number)': ec_object
    }
    human_readable = tableToMarkdown('Pull Request Files', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def list_issue_comments_command():
    args = demisto.args()
    issue_number = args.get('issue_number')
    response = list_issue_comments(issue_number)

    ec_object = [format_comment_outputs(comment) for comment in response]
    ec = {
        'GitHub.Comment(val.ID === obj.ID)': ec_object
    }
    human_readable = tableToMarkdown('Comments', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def create_comment_command():
    args = demisto.args()
    issue_number = args.get('issue_number')
    body = args.get('body')
    response = create_comment(issue_number, body)

    ec_object = format_comment_outputs(response)
    ec = {
        'GitHub.Comment(val.ID === obj.ID)': ec_object
    }
    human_readable = tableToMarkdown('Created Comment', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def request_review_command():
    args = demisto.args()
    pull_number = args.get('pull_number')
    reviewers = argToList(args.get('reviewers'))
    response = request_review(pull_number, reviewers)

    requested_reviewers = response.get('requested_reviewers', [])
    formatted_requested_reviewers = [
        {
            'Login': reviewer.get('login'),
            'Type': reviewer.get('type')
        }
        for reviewer in requested_reviewers
    ]
    ec_object = {
        'Number': response.get('number'),
        'RequestedReviewer': formatted_requested_reviewers
    }
    ec = {
        'GitHub.PR(val.Number === obj.Number)': ec_object
    }
    human_readable = tableToMarkdown(f'Requested Reviewers for {response.get("number")}', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def get_team_membership_command():
    args = demisto.args()
    team_id = 0
    try:
        team_id = int(args.get('team_id'))
    except ValueError as e:
        return_error('"team_id" command argument must be an integer value.', e)
    user_name = args.get('user_name')
    response = get_team_membership(team_id, user_name)

    ec_object = {
        'Role': response.get('role'),
        'State': response.get('state'),
        'ID': team_id
    }
    ec = {
        'GitHub.Team': ec_object
    }
    human_readable = tableToMarkdown(f'Team Membership of {user_name}', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def get_branch_command():
    args = demisto.args()
    branch_name = args.get('branch_name')
    response = get_branch(branch_name)

    commit = response.get('commit', {})
    author = commit.get('author', {})
    parents = commit.get('parents', [])
    ec_object = {
        'Name': response.get('name'),
        'CommitSHA': commit.get('sha'),
        'CommitNodeID': commit.get('node_id'),
        'CommitAuthorID': author.get('id'),
        'CommitAuthorLogin': author.get('login'),
        'CommitParentSHA': [parent.get('sha') for parent in parents],
        'Protected': response.get('protected')
    }
    ec = {
        'GitHub.Branch(val.Name === obj.name && val.CommitSHA === obj.CommitSHA)': ec_object
    }
    human_readable = tableToMarkdown('Branch', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def create_branch_command():
    args = demisto.args()
    branch_name = args.get('branch_name')
    sha = args.get('sha')
    response = create_branch(branch_name, sha)

    ec_object = {
        'Ref': response.get('ref'),
        'NodeID': response.get('node_id')
    }
    ec = {
        'GitHub.Branch(val.Ref === obj.Ref && val.NodeID === obj.NodeID)': ec_object
    }
    human_readable = tableToMarkdown('Created Branch Details', ec_object, removeNull=True)
    return_outputs(readable_output=human_readable, outputs=ec, raw_response=response)


def get_stale_prs_command():
    args = demisto.args()
    results = get_stale_prs(args)
    if results:
        formatted_results = []
        for pr in results:
            requested_reviewers = [
                requested_reviewer.get('login') for requested_reviewer in pr.get('requested_reviewers', [])
            ]
            formatted_pr = {
                'URL': pr.get('html_url'),
                'Number': pr.get('number'),
                'RequestedReviewer': requested_reviewers
            }
            formatted_results.append(formatted_pr)
        ec = {
            'GitHub.PR(val.Number === obj.Number)': formatted_results
        }
        human_readable = tableToMarkdown('Stale PRs', formatted_results, removeNull=True)
        return_outputs(readable_output=human_readable, outputs=ec, raw_response=results)
    else:
        demisto.results('No stale external PRs found')



def create_command():
    args = demisto.args()
    response = create_issue(args.get('title'), args.get('body'),
                            args.get('labels'), args.get('assignees'))
    issue = issue_format(response)
    context_create_issue(response, issue)


def close_command():
    id = demisto.args().get('ID')
    response = close_issue(id)
    issue = issue_format(response)
    context_create_issue(response, issue)


def update_command():
    args = demisto.args()
    response = update_issue(args.get('ID'), args.get('title'), args.get('body'), args.get('state'),
                            args.get('labels'), args.get('assignees'))
    issue = issue_format(response)
    context_create_issue(response, issue)


def list_all_command():
    state = demisto.args().get('state')
    limit = int(demisto.args().get('limit'))
    if limit > 200:
        limit = 200

    response = list_all_issue(state)
    create_issue_table(response, response, limit)


def search_command():
    q = demisto.args().get('query')
    limit = int(demisto.args().get('limit'))
    if limit > 200:
        limit = 200

    response = search_issue(q)
    create_issue_table(response['items'], response, limit)


def fetch_incidents_command():
    last_run = demisto.getLastRun()
    now = datetime.now()
    if last_run and 'start_time' in last_run:
        start_time = datetime.strptime(last_run.get('start_time'), '%Y-%m-%dT%H:%M:%SZ')

    else:
        time_range_start, _ = parse_date_range(FETCH_TIME)
        start_delta = now - time_range_start
        start_time = now - start_delta

    last_time = start_time

    opened_query = 'repo:{USER}/{REPOSITORY} is:open updated:>{timestamp} is:pr -label:{label}'
    opened_prs = get_relevant_prs(start_time, CONTRIBUTION_LABEL, opened_query)

    time_range_start, _ = parse_date_range(STALE_TIME)
    inactive_query = 'repo:{USER}/{REPOSITORY} is:open updated:<{timestamp} is:pr label:{label}'
    inactive_prs = get_relevant_prs(time_range_start, CONTRIBUTION_LABEL, inactive_query)
    for pr in inactive_prs:
        # demisto.info('PR: ' + json.dumps(pr, indent=4))
        issue_number = pr.get('number')
        sha = pr.get('head', {}).get('sha')
        demisto.info('SHA: ' + sha)
        commit_data = get_commit(sha)
        # demisto.info('COMMIT: ', json.dumps(commit_data, indent=4))
        reviews_data = list_pr_reviews(issue_number)
        comments_data = list_issue_comments(issue_number)
        alert_appropriate_party(pr, commit_data, reviews_data, comments_data)

    # label and assign reviewer to new external PRs
    incidents = []
    for pr in opened_prs:
        updated_at_str = pr.get('created_at')
        updated_at = datetime.strptime(updated_at_str, '%Y-%m-%dT%H:%M:%SZ')
        pr_opener = pr.get('head', {}).get('user', {}).get('login')
        try:
            not_content_member = get_team_membership(CONTENT_TEAM_ID, pr_opener).get('state', '') != 'active'
        except Exception:
            not_content_member = True
        demisto.info(f'not_content_member: {not_content_member}')
        is_fork = pr.get('head', {}).get('repo', {}).get('fork')
        if is_fork or not_content_member:
            issue_number = pr.get('number')
            add_label(issue_number, [CONTRIBUTION_LABEL])
            selected_reviewer = REVIEWERS[issue_number % len(REVIEWERS)]
            create_comment(issue_number, WELCOME_MSG.replace('reviewer', selected_reviewer))
            request_review(issue_number, [selected_reviewer])
            check_pr_files(issue_number, pr.get('head', {}).get('user', {}).get('login', ''))
        if updated_at > start_time:
            inc = {
                'name': pr.get('url'),
                'occurred': updated_at_str,
                'rawJSON': json.dumps(pr)
            }
            incidents.append(inc)
            if updated_at > last_time:
                last_time = updated_at

    demisto.setLastRun({'start_time': datetime.strftime(last_time, '%Y-%m-%dT%H:%M:%SZ')})
    demisto.incidents(incidents)


''' COMMANDS MANAGER / SWITCH PANEL '''

COMMANDS = {
    'test-module': test_module,
    'fetch-incidents': fetch_incidents_command,
    'GitHub-create-issue': create_command,
    'GitHub-close-issue': close_command,
    'GitHub-update-issue': update_command,
    'GitHub-list-all-issues': list_all_command,
    'GitHub-search-issues': search_command,
    'GitHub-get-download-count': get_download_count,
    'GitHub-get-stale-prs': get_stale_prs_command,
    'GitHub-get-branch': get_branch_command,
    'GitHub-create-branch': create_branch_command,
    'GitHub-get-team-membership': get_team_membership_command,
    'GitHub-request-review': request_review_command,
    'GitHub-create-comment': create_comment_command,
    'GitHub-list-issue-comments': list_issue_comments_command,
    'GitHub-list-pr-files': list_pr_files_command,
    'GitHub-list-pr-reviews': list_pr_reviews_command,
    'GitHub-get-commit': get_commit_command,
    'GitHub-add-label': add_label_command,
    'GitHub-get-pull-request': get_pull_request_command
}


'''EXECUTION'''


def main():
    handle_proxy()
    cmd = demisto.command()
    LOG(f'command is {cmd}')
    try:
        if cmd in COMMANDS.keys():
            COMMANDS[cmd]()
    except Exception as e:
        # raise e
        return_error(str(e))

# python2 uses __builtin__ python3 uses builtins
if __name__ == '__builtin__' or __name__ == 'builtins':
    main()
