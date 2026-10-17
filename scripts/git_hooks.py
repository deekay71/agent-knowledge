#!/usr/bin/env python3
"""Opt-in repository-local Git hooks; validate the staged snapshot, never staged code."""
import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

# This is the trusted working-checkout validator, not scripts from the index.
import wiki

HOOKS_PATH = '.githooks'
STATE_NAME = 'wiki-hooks-install.json'
HOOK_NAMES = ('pre-commit', 'pre-merge-commit')


def git_run(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True)


def root_path(root):
    root = root.resolve()
    wiki.repo(root)
    return root


def git_path(root, name, common=False):
    if common:
        path = Path(wiki.git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')) / name
    else:
        path = Path(wiki.git(root, 'rev-parse', '--path-format=absolute', '--git-path', name))
    return path


def safe_name(value):
    """Git object names are untrusted paths, including on case-insensitive macOS."""
    if not value or '\x00' in value or '\\' in value:
        raise ValueError('Unsafe staged path')
    parts = value.split('/')
    if PurePosixPath(value).is_absolute() or any(
        part in ('', '.', '..') or part.casefold() == '.git' for part in parts
    ):
        raise ValueError('Unsafe staged path: ' + value)
    return parts


def entries(root):
    result = []
    names = set()
    for item in filter(None, wiki.git_bytes(root, 'ls-files', '--stage', '-z').split(b'\0')):
        head, raw_name = item.split(b'\t', 1)
        mode, oid, stage = head.decode('ascii').split()
        name = raw_name.decode('utf-8')
        safe_name(name)
        if stage != '0':
            raise ValueError('Unresolved Git index entries: resolve and stage the merge first')
        # Reject case collisions even when tests run on a case-sensitive filesystem.
        folded = name.casefold()
        if folded in names:
            raise ValueError('Case-colliding staged paths: ' + name)
        names.add(folded)
        result.append((name, mode, oid))
    return result


def baseline_commits(root):
    head = git_run(root, 'rev-parse', '--verify', 'HEAD')
    if head.returncode:
        # Only a genuinely unborn attached branch may lack HEAD.
        branch = git_run(root, 'symbolic-ref', '--quiet', 'HEAD')
        if branch.returncode or git_run(root, 'show-ref', '--verify', '--quiet', branch.stdout.decode().strip()).returncode != 1:
            raise ValueError('Cannot determine HEAD baseline')
        parents = []
    else:
        parents = [head.stdout.decode().strip()]
    merge = git_path(root, 'MERGE_HEAD')
    if merge.exists():
        if merge.is_symlink() or not merge.is_file():
            raise ValueError('Unsafe MERGE_HEAD')
        for value in merge.read_text().splitlines():
            sha = wiki.git(root, 'rev-parse', '--verify', '--end-of-options', value + '^{commit}')
            if sha not in parents:
                parents.append(sha)
    return parents


def check_history(root, snapshot, revision, incoming=False):
    errors = []
    try:
        for entry in filter(None, wiki.git_bytes(root, 'ls-tree', '-rz', revision, '--', 'raw').split(b'\0')):
            info, raw_name = entry.split(b'\t', 1)
            mode, kind, oid = info.decode('ascii').split()
            name = raw_name.decode('utf-8')
            safe_name(name)
            if mode not in ('100644', '100755') or kind != 'blob':
                raise ValueError('Baseline raw is not a regular file: ' + name)
            if wiki.metadata_path(snapshot, name, 'raw').read_bytes() != wiki.git_bytes(root, 'cat-file', 'blob', oid):
                errors.append('Immutable source changed: ' + name)
        # An existing non-wiki repository may acquire its first wiki on a contrib branch.
        old = git_run(root, 'show', revision + ':wiki/log.md')
        if old.returncode:
            # Treat no archived raw/log as a first import; malformed existing wiki fails closed.
            if wiki.git_bytes(root, 'ls-tree', '-rz', revision, '--', 'raw', 'wiki'):
                raise ValueError('Baseline contains knowledge but is missing wiki/log.md')
            return errors
        events = wiki.log_events(old.stdout)
        new = wiki.metadata_path(snapshot, 'wiki/log.md').read_bytes()
        if incoming:
            current = iter(wiki.log_events(new))
            for event in events:
                if not any(candidate == event for candidate in current):
                    errors.append('Incoming log event lost or reordered: ' + revision)
                    break
        elif not new.startswith(old.stdout):
            errors.append('Log is not append-only relative to HEAD')
    except (ValueError, OSError, UnicodeError) as error:
        errors.append('History check: ' + str(error))
    return errors


def check_staged_vault(snapshot):
    """Load the live trusted validator; staged exporter scripts remain inert data."""
    runtime_root = Path(__file__).resolve().parents[1]
    exporter_path = wiki.metadata_path(runtime_root, 'scripts/export_vault.py')
    spec = importlib.util.spec_from_file_location('wiki_hook_vault_validator', exporter_path)
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load trusted vault validator')
    exporter = importlib.util.module_from_spec(spec)
    prior = sys.modules.get(spec.name)
    sys.modules[spec.name] = exporter
    try:
        spec.loader.exec_module(exporter)
        return exporter.check(snapshot, snapshot / 'vault')
    finally:
        if prior is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = prior


def check(root, merge=False):
    root = root_path(root)
    staged = entries(root)
    if not any(name.startswith('wiki/') for name, _, _ in staged) or not any(name.startswith('raw/') for name, _, _ in staged):
        raise ValueError('Target must contain staged raw/ and wiki/ knowledge; missing directory or unrelated repository')
    parents = baseline_commits(root)
    staged_vault = any(name == 'vault' or name.startswith('vault/') for name, _, _ in staged)
    if parents and not staged_vault and wiki.git_bytes(root, 'ls-tree', '-rz', parents[0], '--', 'vault'):
        raise ValueError('Managed vault removed from the staged snapshot; regenerate and stage vault/ instead of bypassing validation')
    if merge and not git_path(root, 'MERGE_HEAD').exists():
        raise ValueError('Automatic merge paused: Git has not exposed all merge parents yet. '
                         'Run git commit to validate the prepared merge against every parent, '
                         'or use git merge --no-commit followed by git commit. '
                         'No files were changed by this hook.')
    changed = wiki.git_bytes(root, 'diff', '--cached', '--name-only', '-z', *(parents[:1]), '--', 'raw', 'wiki')
    if changed:
        wiki.branch_guard(root)
    with tempfile.TemporaryDirectory(prefix='wiki-staged-') as directory:
        snapshot = Path(directory).resolve()
        for name, mode, oid in staged:
            knowledge = name.split('/')[0] in ('raw', 'wiki', 'vault')
            if mode not in ('100644', '100755'):
                if knowledge:
                    raise ValueError('Staged knowledge must be regular files, not symlink/gitlink: ' + name)
                # Do not materialize any symlink/gitlink. References to skipped files fail lint.
                continue
            target = snapshot.joinpath(*safe_name(name))
            target.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation rejects directory/file collisions; no checkout or staged execution.
            with target.open('xb') as handle:
                handle.write(wiki.git_bytes(root, 'cat-file', 'blob', oid))
        result = wiki.lint(snapshot)
        if staged_vault:
            try:
                result['vault_check'] = check_staged_vault(snapshot)
            except (ValueError, OSError) as error:
                result['errors'].append('Staged vault check: ' + str(error))
        history_errors = []
        for number, parent in enumerate(parents):
            history_errors.extend(check_history(root, snapshot, parent, incoming=number > 0))
        result['errors'].extend(history_errors)
        if parents:
            result['warnings'] = [w for w in result['warnings'] if not w.startswith('History not checked:')]
        else:
            result['warnings'] = [w for w in result['warnings'] if not w.startswith('History not checked:')]
            result['warnings'].append('Initial commit: no prior history exists to compare')
        result['history_checked'] = bool(parents) and not history_errors
        result['baselines'] = parents
        result['validation'] = 'staged snapshot; structural checks only, not semantic truth or sharing authorization'
        return result


def config_values(root, local=False):
    args = ['config'] + (['--local'] if local else []) + ['--null', '--get-all', 'core.hooksPath']
    result = git_run(root, *args)
    if result.returncode not in (0, 1):
        raise ValueError(result.stderr.decode(errors='replace'))
    return result.stdout.decode('utf-8').rstrip('\0').split('\0') if result.returncode == 0 else []


def read_state(root):
    path = git_path(root, STATE_NAME, common=True)
    if path.is_symlink():
        raise ValueError('Installation state must not be a symlink')
    if not path.exists():
        return None
    value = wiki.json_load(path.read_text())
    if value != {'version': 1, 'hooks_path': HOOKS_PATH, 'previous_local': []}:
        raise ValueError('Unknown installation state; preserve config and inspect manually')
    return value


def validate_runtime(root):
    for name in ('scripts/wiki.py', 'scripts/git_hooks.py', '.githooks/pre-commit', '.githooks/pre-merge-commit'):
        path = wiki.metadata_path(root, name)
        if name.startswith('.githooks/') and not os.access(path, os.X_OK):
            raise ValueError('Hook is not executable: ' + name)
    for name in ('raw', 'wiki'):
        if not wiki.inside(root, name).is_dir():
            raise ValueError('Missing knowledge directory: ' + name)
    if (root / 'vault').exists() or (root / 'vault').is_symlink() or wiki.git_bytes(root, 'ls-files', '-z', '--', 'vault'):
        wiki.metadata_path(root, 'scripts/export_vault.py')


def status(root):
    root = root_path(root)
    state = read_state(root)
    local, effective = config_values(root, True), config_values(root)
    active = bool(state) and local == [HOOKS_PATH] and effective[-1:] == [HOOKS_PATH]
    runtime_error = None
    try:
        validate_runtime(root)
    except (ValueError, OSError) as error:
        runtime_error = str(error)
    return {'installed': bool(state), 'active': active and runtime_error is None,
            'local_hooks_path': local, 'effective_hooks_paths': effective,
            'runtime_error': runtime_error, 'scope': 'repository-local config; shared by linked worktrees',
            'hooks': list(HOOK_NAMES)}


def install(root):
    root = root_path(root)
    with wiki.mutation_lock(root):
        validate_runtime(root)
        state = read_state(root)
        local, effective = config_values(root, True), config_values(root)
        if state:
            if local != [HOOKS_PATH] or effective[-1:] != [HOOKS_PATH]:
                raise ValueError('Hook config changed since installation; preserve it and reconcile manually')
            return status(root)
        if effective or local:
            raise ValueError('Existing/inherited core.hooksPath is configured; refusing to overwrite custom hooks')
        default_hooks = git_path(root, 'hooks', common=True)
        if default_hooks.exists():
            for item in default_hooks.iterdir():
                if not item.name.endswith('.sample') and os.access(item, os.X_OK) and item.is_file():
                    raise ValueError('Existing executable hook must be integrated manually: ' + item.name)
        state_path = git_path(root, STATE_NAME, common=True)
        with state_path.open('x') as handle:
            json.dump({'version': 1, 'hooks_path': HOOKS_PATH, 'previous_local': []}, handle)
        try:
            wiki.git(root, 'config', '--local', '--add', 'core.hooksPath', HOOKS_PATH)
        except (ValueError, OSError):
            state_path.unlink()
            raise
        return status(root)


def uninstall(root):
    root = root_path(root)
    with wiki.mutation_lock(root):
        state = read_state(root)
        if not state:
            return status(root)
        if config_values(root, True) != [HOOKS_PATH]:
            raise ValueError('Local hook config changed; refusing to overwrite it')
        wiki.git(root, 'config', '--local', '--unset-all', 'core.hooksPath')
        git_path(root, STATE_NAME, common=True).unlink()
        return status(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest='command', required=True)
    check_parser = commands.add_parser('check')
    check_parser.add_argument('--merge', action='store_true', help='pre-merge-commit guard; require visible MERGE_HEAD parents')
    for name in ('install', 'status', 'uninstall'):
        commands.add_parser(name)
    args = parser.parse_args()
    try:
        result = check(args.root, args.merge) if args.command == 'check' else globals()[args.command](args.root)
        print(json.dumps(result, indent=2))
        return int(bool(result.get('errors')))
    except (ValueError, OSError, UnicodeError) as error:
        print('Wiki hook ERROR: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
