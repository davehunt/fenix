# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Decision task for nightly releases.
"""

from __future__ import print_function

import argparse
import os
import taskcluster

from lib.gradle import get_build_variants, get_geckoview_versions
from lib.tasks import (
    fetch_mozharness_task_id,
    get_architecture_and_build_type_from_variant,
    schedule_task_graph,
    TaskBuilder,
)
from lib.chain_of_trust import (
    populate_chain_of_trust_task_graph,
    populate_chain_of_trust_required_but_unused_files
)

REPO_URL = os.environ.get('MOBILE_HEAD_REPOSITORY')
COMMIT = os.environ.get('MOBILE_HEAD_REV')
PR_TITLE = os.environ.get('GITHUB_PULL_TITLE', '')
SHORT_HEAD_BRANCH = os.environ.get('SHORT_HEAD_BRANCH')

# If we see this text inside a pull request title then we will not execute any tasks for this PR.
SKIP_TASKS_TRIGGER = '[ci skip]'


BUILDER = TaskBuilder(
    task_id=os.environ.get('TASK_ID'),
    repo_url=REPO_URL,
    git_ref=os.environ.get('MOBILE_HEAD_BRANCH'),
    short_head_branch=SHORT_HEAD_BRANCH,
    commit=COMMIT,
    owner="fenix-eng-notifications@mozilla.com",
    source='{}/raw/{}/.taskcluster.yml'.format(REPO_URL, COMMIT),
    scheduler_id=os.environ.get('SCHEDULER_ID', 'taskcluster-github'),
    tasks_priority=os.environ.get('TASKS_PRIORITY'),
    date_string=os.environ.get('BUILD_DATE'),
    trust_level=os.environ.get('TRUST_LEVEL'),
)


def pr_or_push(is_push):
    if not is_push and SKIP_TASKS_TRIGGER in PR_TITLE:
        print("Pull request title contains", SKIP_TASKS_TRIGGER)
        print("Exit")
        return {}

    variants = get_build_variants()
    geckoview_nightly_version = get_geckoview_versions()['nightly']
    mozharness_task_id = fetch_mozharness_task_id(geckoview_nightly_version)
    gecko_revision = taskcluster.Queue().task(mozharness_task_id)['payload']['env']['GECKO_HEAD_REV']

    build_tasks = {}
    signing_tasks = {}
    other_tasks = {}

    for variant in variants:
        assemble_task_id = taskcluster.slugId()
        build_tasks[assemble_task_id] = BUILDER.craft_assemble_task(variant)
        build_tasks[taskcluster.slugId()] = BUILDER.craft_test_task(variant)

        architecture, build_type = get_architecture_and_build_type_from_variant(variant)
        # autophone only supports arm and aarch64, so only sign/perftest those builds
        if (
            is_push and
            build_type == 'releaseRaptor' and
            architecture in ('arm', 'aarch64') and
            SHORT_HEAD_BRANCH == 'master'
        ):
            signing_task_id = taskcluster.slugId()
            signing_tasks[signing_task_id] = BUILDER.craft_master_commit_signing_task(assemble_task_id, variant)

            ALL_RAPTOR_CRAFT_FUNCTIONS = [
                BUILDER.craft_raptor_tp6m_cold_task(for_suite=i)
                for i in range(1, 11)
            ]
            for craft_function in ALL_RAPTOR_CRAFT_FUNCTIONS:
                args = (signing_task_id, mozharness_task_id, variant, gecko_revision)
                other_tasks[taskcluster.slugId()] = craft_function(*args)
                # we also want the arm APK to be tested on 64-bit-devices
                if architecture == 'arm':
                    other_tasks[taskcluster.slugId()] = craft_function(*args, force_run_on_64_bit_device=True)

    for craft_function in (
        BUILDER.craft_detekt_task,
        BUILDER.craft_ktlint_task,
        BUILDER.craft_lint_task,
        BUILDER.craft_compare_locales_task,
    ):
        other_tasks[taskcluster.slugId()] = craft_function()

    return (build_tasks, signing_tasks, other_tasks)


def nightly(track):
    is_staging = track == 'staging-nightly'
    architectures = ['x86', 'arm', 'aarch64']
    apk_paths = ["public/target.{}.apk".format(arch) for arch in architectures]

    build_tasks = {}
    signing_tasks = {}
    push_tasks = {}

    build_task_id = taskcluster.slugId()
    build_tasks[build_task_id] = BUILDER.craft_assemble_nightly_task(architectures, is_staging)

    signing_task_id = taskcluster.slugId()
    signing_tasks[signing_task_id] = BUILDER.craft_nightly_signing_task(
        build_task_id,
        apk_paths=apk_paths,
        is_staging=is_staging,
    )

    push_task_id = taskcluster.slugId()
    push_tasks[push_task_id] = BUILDER.craft_push_task(
        signing_task_id,
        apks=apk_paths,
        is_staging=is_staging,
    )

    return (build_tasks, signing_tasks, push_tasks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Creates and submit a graph of tasks on Taskcluster.'
    )

    subparsers = parser.add_subparsers(dest='command')

    subparsers.add_parser('pull-request')
    subparsers.add_parser('push')
    release_parser = subparsers.add_parser('release')

    release_parser.add_argument('--nightly', action="store_true", default=False)
    release_parser.add_argument(
        '--track', action="store", choices=['nightly', 'staging-nightly'], required=True
    )

    result = parser.parse_args()

    command = result.command
    taskcluster_queue = taskcluster.Queue({'baseUrl': 'http://taskcluster/queue/v1'})

    if command == 'pull-request':
        ordered_groups_of_tasks = pr_or_push(False)
    elif command == 'push':
        ordered_groups_of_tasks = pr_or_push(True)
    elif command == 'release':
        ordered_groups_of_tasks = nightly(result.track)
    else:
        raise Exception('Unsupported command "{}"'.format(command))

    full_task_graph = schedule_task_graph(ordered_groups_of_tasks)

    populate_chain_of_trust_task_graph(full_task_graph)
    populate_chain_of_trust_required_but_unused_files()
