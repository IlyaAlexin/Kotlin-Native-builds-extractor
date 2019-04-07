import argparse
import base64
import json
import logging
import os
import re
import time

import requests

from github import Github

logger = logging.getLogger('Logger')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

multiplatform_projects = []
processed_files = []


def get_github_tree(repository):
    sha = repository.get_branch('master').commit.sha
    return repository.get_git_tree(sha=sha, recursive=True)


def find_gradle_build_files(github_tree):
    build_files = []
    for file in github_tree.tree:
        if 'build.gradle' in file.path:
            logger.info("{} is a gradle build file".format(file.path))
            build_files.append(file)
    return build_files


def get_build_file(repository, sha):
    blob = repository.get_git_blob(sha=sha)
    content = base64.standard_b64decode(blob.content).decode('utf-8')
    return content


def get_release(repository):
    try:
        release = repository.get_latest_release()
        logger.info("Release: {}".format(release))
        if release:
            logger.info('Release is found')
            assets = release.get_assets()
            for asset in assets:
                logger.info(asset)
    except Exception as exception:
        logger.error('Latest release is not found {}. Error: {}'.format(repo['full_name'], exception))


def check_multiplatform_pattern(build_file, pattern):
    res = re.search(pattern, build_file)
    if res != None:
        logger.info(build_file)
        return True
    else:
        return False


def check_multiplatform(build_file):
    is_multiplatform = False
    if check_multiplatform_pattern(build_file, "org.jetbrains.kotlin.multiplatform"):
        is_multiplatform = True
    else:
        if check_multiplatform_pattern(build_file, "kotlin-multiplatform"):
            is_multiplatform = True
        else:
            if check_multiplatform_pattern(build_file, "kotlin-platform-common"):
                is_multiplatform = True
            else:
                if check_multiplatform_pattern(build_file, "kotlin(\"multiplatform\")"):
                    is_multiplatform = True
    return is_multiplatform


def get_requests_limit(github_api, user, password):
    url = '{github}/rate_limit'.format(github=github_api)
    response = requests.get(url, auth=(user, password)).json()
    return int(response['rate']['remaining'])


if __name__ == '__main__':
    args_holder = argparse.ArgumentParser()
    args_holder.add_argument('--user', '-u', help='Username to access GitHub REST API')
    args_holder.add_argument('--password', '-p', help='Password to access GitHUb REST API')
    args_holder.add_argument('--output', '-o', help='File to save multiplatform projects links')
    args_holder.add_argument('--repos_dir', '-r', help='Directory with repositories list')
    args_holder.add_argument('--processed_list', '-l', help='File to collect processed repositories')
    args_holder.add_argument('--api', '-a', help='GitHub api', default='https://api.github.com')

    args = args_holder.parse_args()
    github_endpoint = args.api
    result_file = args.output  #  'C:\\Users\\alexii\\llvm-parser\\result.json'
    processed_repos = args.processed_list  #  'C:\\Users\\alexii\\llvm-parser\\errors.json'
    repos_address = args.repos_dir  #  'C:\\Users\\alexii\\llvm-parser\\search_results_31.05-04.10'

    github_api = Github(args.user, args.password)
    logger.info(github_api)
    with open(result_file, mode='w', encoding='utf-8') as f:
        json.dump([], f)
    with open(processed_repos, mode='w', encoding='utf-8') as f:
        json.dump([], f)

    repos_counter = 0
    for _, _, files in os.walk(repos_address):
        for filename in files:
            logger.info("{} is being processed".format(filename))
            filename = "{}\\{}".format(repos_address, filename)
            start = time.time()
            with open(filename) as repos_file:
                repos_list = json.load(repos_file)['items']
                logger.info(repos_list)
                for repo in repos_list:
                    try:
                        repository = github_api.get_repo(repo['full_name'])
                        # get_release(repository)
                        repos_counter += 1
                        logger.info('Current repository name: {}'.format(repo['full_name']))

                        remaining_requests = get_requests_limit(github_endpoint, args.user, args.password)
                        logger.info(remaining_requests)
                        if remaining_requests > 5:
                            repository = github_api.get_repo(repo['full_name'])
                            github_tree = get_github_tree(repository)
                            files = find_gradle_build_files(github_tree)

                            multiplatform_trigger = False
                            for build_file in files:
                                build_content = get_build_file(repository, build_file.sha)
                                if check_multiplatform(build_content):
                                    multiplatform_trigger = True
                                    repo['build_file'] = build_file.path
                                    multiplatform_projects.append(repo)
                                    logger.info('Build file {} is multiplatform'.format(build_file.path))
                                    with open(result_file, mode='w', encoding='utf-8') as f:
                                        json.dump(multiplatform_projects, f, indent=2)
                            if not multiplatform_trigger:
                                logger.info('Repo {} doesn\'t contain plugins'.format(repo['full_name']))
                        else:
                            requests_end = time.time()
                            period = requests_end - start
                            logger.info('Requests ended in {} '.format(period))
                            while remaining_requests < 1000:
                                logger.info('No more requests for this hour')
                                time.sleep(60)
                                remaining_requests = get_requests_limit(github_endpoint, args.user, args.password)
                            logger.info('{} are available for the next hour'.format(remaining_requests))
                            start = time.time()
                    except Exception as exception:
                        logger.error('Repo is not found {}. Error: {}'.format(repo['full_name'], exception))
            logger.info('Number of processed repos: {}'.format(repos_counter))
            processed_files.append(filename)
            with open(processed_repos, mode='w') as f:
                json.dump(processed_files, f)
