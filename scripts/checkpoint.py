#!/usr/bin/env python3
"""Save a Git checkpoint without changing the working tree or real index."""
import argparse
import datetime
import os
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,60}', args.label):
        parser.error('label must contain lowercase letters, digits and hyphens')
    root = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='coursepilot-checkpoint-') as directory:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(directory, 'index'))
        def git(*arguments, **kwargs):
            return subprocess.check_output(['git', *arguments], cwd=root, env=env, text=True, **kwargs).strip()
        head = git('rev-parse', 'HEAD')
        git('read-tree', head)
        git('add', '-A')
        tree = git('write-tree')
        commit = git('commit-tree', tree, '-p', head, input=f'checkpoint: {args.label}\n')
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        ref = f'refs/checkpoints/coursepilot/{stamp}-{args.label}'
        git('update-ref', ref, commit)
        print(f'{ref}\n{commit}')


if __name__ == '__main__':
    main()
