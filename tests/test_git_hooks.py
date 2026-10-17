"""Real Git integration: hooks inspect the index and never alter working content."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import demo
import fixtures
import git_hooks
import wiki


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wiki hooks tests ')
        self.addCleanup(self.temp.cleanup)
        self.sandbox = Path(self.temp.name).resolve()
        self.root = self.sandbox / 'repository with spaces'
        self.root.mkdir()
        wiki.git(self.root, 'init', '-b', 'contrib/test')
        wiki.git(self.root, 'config', 'user.name', 'Local Test')
        wiki.git(self.root, 'config', 'user.email', 'local@example.invalid')
        # Real hook runtime is present in fixture checkout; no global hook activation.
        for folder in ('scripts', '.githooks'):
            (self.root / folder).mkdir()
        for name in ('wiki.py', 'git_hooks.py'):
            shutil.copy2(REPO / 'scripts' / name, self.root / 'scripts' / name)
        for name in git_hooks.HOOK_NAMES:
            shutil.copy2(REPO / '.githooks' / name, self.root / '.githooks' / name)
        fixtures.seed(self.root)
        self.base = demo.commit(self.root, 'Baseline')

    def run_git(self, *args, expected=0, env=None, cwd=None):
        result = subprocess.run(['git', *args], cwd=cwd or self.root,
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def cli(self, command, expected=0, **kwargs):
        result = subprocess.run([sys.executable, str(REPO / 'scripts/git_hooks.py'),
                                 '--root', str(self.root), command], capture_output=True, text=True, **kwargs)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def stage(self, *paths):
        wiki.git(self.root, 'add', *paths)

    def errors(self):
        return '\n'.join(git_hooks.check(self.root)['errors'])

    def amend_page(self, key, value):
        path = self.root / 'wiki/concepts/queue.md'
        meta, body = wiki.read_page(path)
        meta[key] = value
        fixtures.write(path, meta, body)

    def test_cli_help_and_status_do_not_install(self):
        for command in ('check', 'install', 'status', 'uninstall'):
            result = subprocess.run([sys.executable, str(REPO / 'scripts/git_hooks.py'), command, '--help'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
        self.assertFalse(json.loads(self.cli('status').stdout)['installed'])
        self.assertEqual(git_hooks.config_values(self.root, True), [])

    def test_staged_invalid_unstaged_valid_blocked(self):
        page = self.root / 'wiki/concepts/queue.md'
        original = page.read_bytes()
        self.amend_page('scope', 'project')
        self.stage('wiki/concepts/queue.md')
        page.write_bytes(original)
        self.assertIn('Project/session', self.errors())
        self.assertEqual(page.read_bytes(), original)

    def test_staged_valid_unstaged_invalid_and_private_untracked_preserved(self):
        wiki.record(self.root, 'maintain', 'Valid staged append')
        self.stage('wiki/log.md')
        self.amend_page('scope', 'project')
        untracked = self.root / 'private.txt'
        untracked.write_bytes(b'only copy of private content')
        (self.root / '.git/info/exclude').write_text('ignored.txt\n')
        ignored = self.root / 'ignored.txt'
        ignored.write_bytes(b'ignored draft')
        page = (self.root / 'wiki/concepts/queue.md').read_bytes()
        self.assertEqual(self.errors(), '')
        self.assertEqual((self.root / 'wiki/concepts/queue.md').read_bytes(), page)
        self.assertEqual(untracked.read_bytes(), b'only copy of private content')
        self.assertEqual(ignored.read_bytes(), b'ignored draft')

    def test_raw_mutation_and_log_rewrite_fail(self):
        raw = self.root / 'raw/fixture-v1.md'
        raw.write_text(raw.read_text() + 'Changed\n')
        self.stage('raw')
        self.assertIn('Immutable source changed', self.errors())
        self.assertFalse(git_hooks.check(self.root)['history_checked'])
        log = self.root / 'wiki/log.md'
        log.write_text('# Wiki log\n')
        self.stage('wiki/log.md')
        self.assertIn('append-only', self.errors())

    def test_staged_raw_deletion_fails(self):
        wiki.git(self.root, 'rm', 'raw/fixture-v1.md')
        with self.assertRaisesRegex(ValueError, 'missing directory'):
            git_hooks.check(self.root)

    def test_symlink_and_gitlink_rejected_without_reading_target(self):
        outside = self.sandbox / 'private.md'
        outside.write_text('private data')
        link = self.root / 'raw/leak.md'
        link.symlink_to(outside)
        self.stage('raw/leak.md')
        with self.assertRaisesRegex(ValueError, 'symlink/gitlink'):
            git_hooks.check(self.root)
        wiki.git(self.root, 'update-index', '--force-remove', 'raw/leak.md')
        wiki.git(self.root, 'update-index', '--add', '--cacheinfo', '160000,' + self.base + ',wiki/nested')
        with self.assertRaisesRegex(ValueError, 'symlink/gitlink'):
            git_hooks.check(self.root)
        self.assertEqual(outside.read_text(), 'private data')

    def test_unsafe_paths_never_extracted(self):
        for name in ('../outside', '/absolute', 'raw/../../private', '.git/config', 'docs/.GIT/config', 'raw\\outside', 'a//b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                git_hooks.safe_name(name)

    def test_staged_scripts_are_not_executed(self):
        source = self.root / 'scripts/wiki.py'
        original = source.read_bytes()
        source.write_text('raise RuntimeError("STAGED CODE RAN")\n')
        self.stage('scripts/wiki.py')
        source.write_bytes(original)
        self.assertEqual(self.errors(), '')

    def test_main_and_detached_knowledge_changes_block_but_docs_allowed(self):
        wiki.git(self.root, 'checkout', '-b', 'main')
        (self.root / 'README.md').write_text('Documentation only\n')
        self.stage('README.md')
        self.assertEqual(self.errors(), '')
        (self.root / 'wiki/log.md').write_bytes(wiki.appended_log(self.root, 'maintain', 'x'))
        self.stage('wiki/log.md')
        with self.assertRaisesRegex(ValueError, 'contrib/'):
            git_hooks.check(self.root)
        wiki.git(self.root, 'checkout', '--detach', self.base)
        with self.assertRaises(ValueError):
            git_hooks.check(self.root)

    def test_alternate_index_is_honored(self):
        index = self.sandbox / 'partial index'
        env = dict(os.environ, GIT_INDEX_FILE=str(index))
        self.run_git('read-tree', 'HEAD', env=env)
        self.amend_page('scope', 'project')
        self.run_git('add', 'wiki/concepts/queue.md', env=env)
        self.assertEqual(self.errors(), '')
        output = self.cli('check', expected=1, env=env)
        self.assertIn('Project/session', output.stdout)

    def test_install_idempotent_uninstall_restores_absent_local_config(self):
        self.assertTrue(git_hooks.install(self.root)['active'])
        self.assertTrue(git_hooks.install(self.root)['active'])
        self.assertEqual(git_hooks.config_values(self.root, True), ['.githooks'])
        self.assertFalse(git_hooks.uninstall(self.root)['installed'])
        self.assertEqual(git_hooks.config_values(self.root, True), [])
        self.assertFalse(git_hooks.uninstall(self.root)['installed'])

    def test_existing_hooks_config_is_preserved(self):
        wiki.git(self.root, 'config', '--local', 'core.hooksPath', 'custom-hooks')
        with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
            git_hooks.install(self.root)
        self.assertEqual(git_hooks.config_values(self.root, True), ['custom-hooks'])
        self.assertFalse(git_hooks.read_state(self.root))

    def test_inherited_hooks_config_is_preserved(self):
        env = dict(os.environ, GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.hooksPath', GIT_CONFIG_VALUE_0='inherited-hooks')
        self.cli('install', expected=2, env=env)
        self.assertEqual(git_hooks.config_values(self.root, True), [])

    def test_executable_default_hook_is_preserved(self):
        path = self.root / '.git/hooks/pre-commit'
        path.write_text('#!/bin/sh\nexit 0\n')
        path.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'Existing executable hook'):
            git_hooks.install(self.root)
        self.assertEqual(path.read_text(), '#!/bin/sh\nexit 0\n')

    def test_missing_or_nonexecutable_runtime_fails_before_config_change(self):
        path = self.root / '.githooks/pre-commit'
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'not executable'):
            git_hooks.install(self.root)
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing regular'):
            git_hooks.install(self.root)
        self.assertEqual(git_hooks.config_values(self.root, True), [])

    def test_uninstall_preserves_config_changed_by_user(self):
        git_hooks.install(self.root)
        wiki.git(self.root, 'config', '--local', 'core.hooksPath', 'user-new-hooks')
        with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
            git_hooks.uninstall(self.root)
        self.assertEqual(git_hooks.config_values(self.root, True), ['user-new-hooks'])
        self.assertTrue(git_hooks.read_state(self.root))

    def test_permission_failure_keeps_config_and_no_marker(self):
        with mock.patch.object(Path, 'open', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                git_hooks.install(self.root)
        self.assertEqual(git_hooks.config_values(self.root, True), [])
        self.assertFalse(git_hooks.read_state(self.root))

    def test_real_commit_blocks_invalid_and_accepts_valid_from_subdirectory(self):
        git_hooks.install(self.root)
        self.amend_page('scope', 'project')
        self.stage('wiki/concepts/queue.md')
        result = self.run_git('commit', '-m', 'Must fail', expected=1, cwd=self.root / 'wiki')
        self.assertIn('Project/session', result.stdout + result.stderr)
        self.assertEqual(wiki.git(self.root, 'rev-parse', 'HEAD'), self.base)
        self.amend_page('scope', 'shared')
        wiki.record(self.root, 'maintain', 'Valid change')
        self.stage('wiki')
        self.run_git('commit', '-m', 'Pass', cwd=self.root / 'wiki')
        self.assertNotEqual(wiki.git(self.root, 'rev-parse', 'HEAD'), self.base)

    def test_real_partial_commit_uses_its_temporary_index(self):
        git_hooks.install(self.root)
        self.amend_page('scope', 'project')
        self.stage('wiki/concepts/queue.md')
        (self.root / 'note.md').write_text('commit only this\n')
        self.stage('note.md')
        self.run_git('commit', '--only', 'note.md', '-m', 'Partial doc commit')
        self.assertIn('wiki/concepts/queue.md', wiki.git(self.root, 'diff', '--cached', '--name-only'))

    def test_initial_commit_no_history(self):
        root = self.sandbox / 'unborn'
        root.mkdir()
        wiki.git(root, 'init', '-b', 'contrib/initial')
        fixtures.seed(root)
        shutil.copytree(self.root / 'scripts', root / 'scripts')
        shutil.copytree(self.root / '.githooks', root / '.githooks')
        wiki.git(root, 'add', '.')
        result = git_hooks.check(root)
        self.assertEqual(result['errors'], [])
        self.assertFalse(result['history_checked'])
        git_hooks.install(root)
        result = subprocess.run(['git', '-c', 'user.name=Local Test', '-c', 'user.email=local@example.invalid',
                                 'commit', '-m', 'First wiki commit'], cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_linked_worktree_uses_shared_install_state_and_own_index(self):
        git_hooks.install(self.root)
        other = self.sandbox / 'linked worktree'
        wiki.git(self.root, 'worktree', 'add', '-b', 'contrib/linked', str(other))
        self.assertTrue(git_hooks.status(other)['active'])
        wiki.record(other, 'maintain', 'linked worktree')
        wiki.git(other, 'add', 'wiki/log.md')
        self.assertEqual(git_hooks.check(other)['errors'], [])
        self.assertEqual(wiki.git(self.root, 'diff', '--cached', '--name-only'), '')
        self.run_git('commit', '-m', 'linked commit', cwd=other)

    def test_merge_preserves_every_parent_and_rejects_lost_events(self):
        wiki.git(self.root, 'checkout', '-b', 'contrib/incoming')
        wiki.record(self.root, 'ingest', 'incoming event')
        incoming = demo.commit(self.root, 'Incoming log')
        incoming_log = (self.root / 'wiki/log.md').read_text()
        wiki.git(self.root, 'checkout', 'contrib/test')
        wiki.record(self.root, 'ingest', 'first parent event')
        demo.commit(self.root, 'First parent')
        first_log = (self.root / 'wiki/log.md').read_text()
        self.run_git('merge', '--no-commit', 'contrib/incoming', expected=1)
        (self.root / 'wiki/log.md').write_text(first_log)
        self.stage('wiki/log.md')
        self.assertIn('Incoming log event lost', self.errors())
        merged = first_log + ''.join(e for e in wiki.log_events(incoming_log.encode()) if e not in wiki.log_events(first_log.encode()))
        (self.root / 'wiki/log.md').write_text(merged)
        self.stage('wiki/log.md')
        result = git_hooks.check(self.root)
        self.assertIn(incoming, result['baselines'])
        self.assertEqual(result['errors'], [])
        git_hooks.install(self.root)
        self.run_git('commit', '-m', 'Merge preserved history')

    def test_pre_merge_commit_hook_runs_on_automatic_merge(self):
        git_hooks.install(self.root)
        wiki.git(self.root, 'checkout', '-b', 'contrib/incoming')
        (self.root / 'incoming.md').write_text('incoming docs\n')
        demo.commit(self.root, 'Incoming docs')
        wiki.git(self.root, 'checkout', 'contrib/test')
        (self.root / 'local.md').write_text('local docs\n')
        demo.commit(self.root, 'Local docs')
        before = wiki.git(self.root, 'rev-parse', 'HEAD')
        result = self.run_git('merge', '--no-ff', 'contrib/incoming', '-m', 'Auto merge', expected=1)
        self.assertIn('Automatic merge paused', result.stdout + result.stderr)
        self.assertEqual(wiki.git(self.root, 'rev-parse', 'HEAD'), before)
        self.assertTrue(git_hooks.git_path(self.root, 'MERGE_HEAD').exists())
        self.assertEqual(len(git_hooks.check(self.root)['baselines']), 2)
        self.run_git('commit', '-m', 'Validated every parent')
        self.assertEqual(len(wiki.git(self.root, 'rev-list', '--parents', '-n', '1', 'HEAD').split()), 3)

    def test_octopus_merge_checks_every_incoming_parent_raw(self):
        for number in (1, 2):
            wiki.git(self.root, 'checkout', '-b', 'contrib/incoming-' + str(number), self.base)
            shutil.copy2(self.root / 'raw/fixture-v1.md', self.root / ('raw/extra-' + str(number) + '.md'))
            demo.commit(self.root, 'Incoming source ' + str(number))
        wiki.git(self.root, 'checkout', 'contrib/test')
        git_hooks.install(self.root)
        self.run_git('merge', '--no-ff', 'contrib/incoming-1', 'contrib/incoming-2', '-m', 'Octopus', expected=1)
        self.assertEqual(len(git_hooks.check(self.root)['baselines']), 3)
        self.assertEqual(self.errors(), '')
        wiki.git(self.root, 'update-index', '--force-remove', 'raw/extra-2.md')
        self.assertIn('Missing regular file: raw/extra-2.md', self.errors())

    def test_unmerged_index_fails_closed(self):
        with mock.patch.object(wiki, 'git_bytes', return_value=(b'100644 ' + b'a' * 40 + b' 2\twiki/page.md\0')):
            with self.assertRaisesRegex(ValueError, 'Unresolved Git index'):
                git_hooks.entries(self.root)

    def test_warnings_remain_visible(self):
        fixtures.seed(self.root, 2)
        self.stage('raw', 'wiki')
        result = json.loads(self.cli('check').stdout)
        self.assertTrue(any('OPEN CONTRADICTION' in value for value in result['warnings']))
        self.assertNotIn('History not checked', str(result['warnings']))


if __name__ == '__main__':
    unittest.main()
