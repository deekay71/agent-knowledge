"""Real staged-vault integration; uses the trusted live exporter, not staged code."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import demo
import fixtures
import git_hooks
import wiki


class VaultHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wiki vault hooks ')
        self.addCleanup(self.temp.cleanup)
        self.sandbox = Path(self.temp.name).resolve()
        self.root = self.sandbox / 'repository with spaces'
        self.root.mkdir()
        wiki.git(self.root, 'init', '-b', 'contrib/vault')
        wiki.git(self.root, 'config', 'user.name', 'Local Test')
        wiki.git(self.root, 'config', 'user.email', 'local@example.invalid')
        for folder in ('scripts', '.githooks'):
            (self.root / folder).mkdir()
        for name in ('wiki.py', 'git_hooks.py', 'export_vault.py'):
            shutil.copy2(REPO / 'scripts' / name, self.root / 'scripts' / name)
        for name in git_hooks.HOOK_NAMES:
            shutil.copy2(REPO / '.githooks' / name, self.root / '.githooks' / name)
        fixtures.seed(self.root)
        self.generate()
        self.base = demo.commit(self.root, 'Wiki and generated vault baseline')

    def generate(self):
        import export_vault
        return export_vault.export(self.root, self.root / 'vault', refresh=(self.root / 'vault').exists())

    def cli(self, command='check', expected=0, env=None):
        result = subprocess.run([sys.executable, str(self.root / 'scripts/git_hooks.py'), command],
                                cwd=self.root, capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def stage(self, *names):
        wiki.git(self.root, 'add', *names)

    def change_source_page(self):
        path = self.root / 'wiki/concepts/queue.md'
        path.write_text(path.read_text() + '\nA new fixture-only explanatory sentence.\n')

    def working_files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*')
                if p.is_file() and '.git' not in p.relative_to(self.root).parts}

    def test_valid_staged_vault_reports_check_without_changing_working_files(self):
        before = self.working_files()
        result = git_hooks.check(self.root)
        self.assertEqual(result['errors'], [])
        self.assertGreater(result['vault_check']['files'], 0)
        self.assertTrue(result['vault_check']['source_digest'])
        self.assertEqual(self.working_files(), before)

    def test_staged_stale_vault_rejected_even_if_working_vault_is_rebuilt(self):
        self.change_source_page()
        self.stage('wiki/concepts/queue.md')
        self.generate()
        before = self.working_files()
        result = git_hooks.check(self.root)
        self.assertIn('Staged vault check:', '\n'.join(result['errors']))
        self.assertEqual(self.working_files(), before)
        self.stage('vault')
        self.assertEqual(git_hooks.check(self.root)['errors'], [])

    def test_staged_valid_vault_ignores_invalid_unstaged_source_and_local_content(self):
        self.change_source_page()
        self.generate()
        self.stage('wiki/concepts/queue.md', 'vault')
        source = self.root / 'wiki/concepts/queue.md'
        source.write_text('Unstaged invalid draft; preserve this text.\n')
        untracked = self.root / 'vault/personal-untracked.md'
        untracked.write_text('Private local note; never implicitly stage it.\n')
        (self.root / '.git/info/exclude').write_text('vault/ignored-note.md\n')
        (self.root / 'vault/ignored-note.md').write_text('Ignored local note\n')
        before = self.working_files()
        self.assertEqual(git_hooks.check(self.root)['errors'], [])
        self.assertEqual(self.working_files(), before)

    def test_whole_vault_removal_cannot_bypass_hook(self):
        wiki.git(self.root, 'rm', '-r', '--cached', 'vault')
        before = self.working_files()
        with self.assertRaisesRegex(ValueError, 'Managed vault removed'):
            git_hooks.check(self.root)
        self.assertEqual(self.working_files(), before)

    def test_nested_vault_symlink_rejected_without_reading_external_target(self):
        target = self.sandbox / 'private.md'
        target.write_text('Keep private\n')
        (self.root / 'vault/leak.md').symlink_to(target)
        self.stage('vault/leak.md')
        with self.assertRaisesRegex(ValueError, 'symlink/gitlink'):
            git_hooks.check(self.root)
        self.assertEqual(target.read_text(), 'Keep private\n')

    def test_vault_root_symlink_rejected(self):
        wiki.git(self.root, 'rm', '-r', '--cached', 'vault')
        original = self.sandbox / 'saved vault'
        (self.root / 'vault').rename(original)
        (self.root / 'vault').symlink_to(original, target_is_directory=True)
        self.stage('vault')
        with self.assertRaisesRegex(ValueError, 'symlink/gitlink'):
            git_hooks.check(self.root)

    def test_nested_vault_gitlink_rejected(self):
        wiki.git(self.root, 'update-index', '--add', '--cacheinfo', '160000,' + self.base + ',vault/nested')
        with self.assertRaisesRegex(ValueError, 'symlink/gitlink'):
            git_hooks.check(self.root)

    def test_staged_exporter_is_never_executed_by_actual_commit_hook(self):
        exporter = self.root / 'scripts/export_vault.py'
        original = exporter.read_bytes()
        exporter.write_text('raise RuntimeError("STAGED EXPORTER WAS EXECUTED")\n')
        self.stage('scripts/export_vault.py')
        exporter.write_bytes(original)
        git_hooks.install(self.root)
        result = subprocess.run(['git', 'commit', '-m', 'Stage inert code fixture'], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('STAGED EXPORTER WAS EXECUTED', result.stdout + result.stderr)

    def test_missing_live_exporter_fails_closed_and_status_reports_runtime_error(self):
        (self.root / 'scripts/export_vault.py').unlink()
        result = self.cli(expected=1)
        self.assertIn('scripts/export_vault.py', result.stdout)
        with self.assertRaisesRegex(ValueError, 'Missing regular file'):
            git_hooks.install(self.root)
        self.assertIn('scripts/export_vault.py', git_hooks.status(self.root)['runtime_error'])

    def test_real_commit_blocks_drift_then_accepts_regenerated_staged_vault(self):
        git_hooks.install(self.root)
        self.change_source_page()
        self.stage('wiki/concepts/queue.md')
        failed = subprocess.run(['git', 'commit', '-m', 'Must fail stale vault'], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        self.assertIn('Staged vault check:', failed.stdout + failed.stderr)
        self.assertEqual(wiki.git(self.root, 'rev-parse', 'HEAD'), self.base)
        self.generate()
        self.stage('vault')
        passed = subprocess.run(['git', 'commit', '-m', 'Fresh staged vault'], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)

    def test_alternate_index_vault_drift_is_checked(self):
        index = self.sandbox / 'alternate index'
        env = dict(os.environ, GIT_INDEX_FILE=str(index))
        subprocess.run(['git', 'read-tree', 'HEAD'], cwd=self.root, env=env, check=True, capture_output=True)
        self.change_source_page()
        subprocess.run(['git', 'add', 'wiki/concepts/queue.md'], cwd=self.root, env=env, check=True, capture_output=True)
        self.assertEqual(git_hooks.check(self.root)['errors'], [])
        result = json.loads(self.cli(expected=1, env=env).stdout)
        self.assertIn('Staged vault check:', '\n'.join(result['errors']))

    def test_staged_vault_plain_file_is_validated_and_rejected(self):
        wiki.git(self.root, 'rm', '-r', '--cached', 'vault')
        (self.root / 'vault').rename(self.sandbox / 'saved vault')
        (self.root / 'vault').write_text('Invalid vault file\n')
        self.stage('vault')
        result = git_hooks.check(self.root)
        self.assertIn('Staged vault check:', '\n'.join(result['errors']))


if __name__ == '__main__':
    unittest.main()
