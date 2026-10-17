"""Real-Git and command-line regressions from the independent safety review."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import demo
import fixtures
import wiki


class GitReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sandbox = Path(self.temp.name).resolve()
        self.root = self.sandbox / 'source'
        self.root.mkdir()
        wiki.git(self.root, 'init', '-b', 'contrib/test')
        fixtures.seed(self.root)
        self.base = demo.commit(self.root, 'Synthetic baseline')

    def cli(self, *args, root=None, expected=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / 'wiki.py'), '--root', str(root or self.root), *map(str, args)],
            text=True, capture_output=True, cwd=self.sandbox,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def snapshot(self, root=None):
        root = root or self.root
        return {
            str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob('*')
            if p.is_file() and '.git' not in p.relative_to(root).parts
        }

    def project(self):
        project = self.sandbox / 'project'
        project.mkdir()
        wiki.git(project, 'init', '-b', 'main')
        wiki.git(project, '-c', 'protocol.file.allow=always', 'submodule', 'add',
                 str(self.root), 'knowledge/shared')
        demo.commit(project, 'Pin shared fixture')
        return project, project / 'knowledge/shared'

    def fetch(self, sub):
        wiki.git(sub, '-c', 'protocol.file.allow=always', 'fetch', 'origin')

    def test_cli_help_lists_real_commands_and_options(self):
        before = self.snapshot()
        help_text = self.cli('--help').stdout
        for command in ('lint', 'index', 'query', 'record', 'worktree', 'pin'):
            with self.subTest(command=command):
                self.assertIn(command, help_text)
                self.assertIn('usage:', self.cli(command, '--help').stdout)
        demo_help = subprocess.run(
            [sys.executable, str(SCRIPTS / 'demo.py'), '--help'], capture_output=True, text=True,
        )
        self.assertEqual(demo_help.returncode, 0)
        self.assertIn('--output OUTPUT', demo_help.stdout)
        self.assertEqual(before, self.snapshot())

    def test_cli_query_index_record_and_saved_lint(self):
        before = self.snapshot()
        result = json.loads(self.cli('query', 'queue', '--version', 'FixtureQueue/1').stdout)
        self.assertEqual(result[0]['claims'][0]['sources'], ['raw/fixture-v1.md'])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(json.loads(self.cli('query', 'queue', '--version', 'unsupported').stdout), [])
        for operation in ('ingest', 'review', 'maintain', 'query'):
            self.cli('record', operation, 'CLI smoke ' + operation)
        self.cli('query', 'queue', '--version', 'FixtureQueue/1', '--record')
        self.cli('index')
        lint = json.loads(self.cli('lint', '--base', self.base, '--record').stdout)
        self.assertEqual(lint['errors'], [])
        self.assertTrue(lint['history_checked'])
        events = [json.loads(line[2:]) for line in (self.root / 'wiki/log.md').read_text().splitlines()[1:]]
        self.assertEqual([event['operation'] for event in events[-7:]],
                         ['ingest', 'review', 'maintain', 'query', 'query', 'index', 'lint'])
        self.assertEqual(wiki.lint(self.root, self.base)['errors'], [])

    def test_cli_worktree_from_clean_main(self):
        wiki.git(self.root, 'branch', '-m', 'main')
        target = self.sandbox / 'main-contribution'
        before = self.snapshot()
        self.cli('worktree', target, 'contrib/from-main')
        self.assertEqual(wiki.git(self.root, 'symbolic-ref', '--short', 'HEAD'), 'main')
        self.assertEqual(wiki.git(target, 'symbolic-ref', '--short', 'HEAD'), 'contrib/from-main')
        self.assertEqual(wiki.git(target, 'rev-parse', 'HEAD'), self.base)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(wiki.git(self.root, 'status', '--porcelain'), '')

    def test_cli_worktree_from_clean_detached_head(self):
        wiki.git(self.root, 'checkout', '--detach', self.base)
        target = self.sandbox / 'detached-contribution'
        self.cli('worktree', target, 'contrib/from-detached')
        self.assertEqual(wiki.git(self.root, 'rev-parse', '--abbrev-ref', 'HEAD'), 'HEAD')
        self.assertEqual(wiki.git(target, 'symbolic-ref', '--short', 'HEAD'), 'contrib/from-detached')
        self.assertEqual(wiki.git(target, 'rev-parse', 'HEAD'), self.base)

    def test_worktree_dirty_source_preserves_changes_and_creates_nothing(self):
        note = self.root / 'draft.txt'
        note.write_text('Keep this unfinished work.\n')
        target = self.sandbox / 'dirty-contribution'
        before = self.snapshot()
        result = self.cli('worktree', target, 'contrib/dirty', expected=2)
        self.assertIn('Dirty tree', result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(before, self.snapshot())
        self.assertEqual(wiki.git(self.root, 'branch', '--list', 'contrib/dirty'), '')

    def test_worktree_nested_existing_and_symlink_destinations_are_rejected(self):
        existing = self.sandbox / 'existing'
        existing.mkdir()
        (existing / 'keep.txt').write_text('preserve')
        alias = self.sandbox / 'alias'
        alias.symlink_to(existing, target_is_directory=True)
        before = self.snapshot()
        for number, target in enumerate((self.root / 'nested', existing, alias / 'child')):
            with self.subTest(target=target):
                branch = f'contrib/invalid-{number}'
                self.cli('worktree', target, branch, expected=2)
                self.assertEqual(wiki.git(self.root, 'branch', '--list', branch), '')
        self.assertEqual((existing / 'keep.txt').read_text(), 'preserve')
        self.assertFalse((self.root / 'nested').exists())
        self.assertFalse((existing / 'child').exists())
        self.assertEqual(before, self.snapshot())

    def test_cli_pin_upgrade_and_rollback_leave_only_reviewable_gitlink(self):
        project, sub = self.project()
        fixtures.seed(self.root, 2)
        second = demo.commit(self.root, 'Add synthetic second version')
        self.fetch(sub)
        project_head = wiki.git(project, 'rev-parse', 'HEAD')
        result = json.loads(self.cli('pin', second, root=project).stdout)
        self.assertEqual(result['selected'], second)
        self.assertEqual(wiki.git(sub, 'rev-parse', 'HEAD'), second)
        self.assertEqual(wiki.git(sub, 'rev-parse', '--abbrev-ref', 'HEAD'), 'HEAD')
        self.assertEqual(wiki.git(project, 'rev-parse', 'HEAD'), project_head)
        self.assertEqual(wiki.git(project, 'diff', '--name-only'), 'knowledge/shared')
        self.assertEqual(wiki.git(project, 'diff', '--cached', '--name-only'), '')
        demo.commit(project, 'Accept new pin')
        self.cli('pin', self.base, root=project)
        self.assertEqual(wiki.git(sub, 'rev-parse', 'HEAD'), self.base)
        self.assertEqual(wiki.git(self.root, 'rev-parse', 'HEAD'), second)

    def test_pin_refuses_ignored_collision_without_losing_bytes_or_head(self):
        (self.root / '.gitignore').write_text('local.txt\n')
        ignored_base = demo.commit(self.root, 'Ignore local work')
        project, sub = self.project()
        (self.root / 'local.txt').write_text('New committed target content\n')
        wiki.git(self.root, 'add', '-f', 'local.txt')
        target = demo.commit(self.root, 'Begin tracking the ignored path')
        self.fetch(sub)
        note = sub / 'local.txt'
        note.write_bytes(b'ONLY COPY OF LOCAL USER NOTES\n')
        before = self.snapshot(sub)
        project_head = wiki.git(project, 'rev-parse', 'HEAD')
        self.assertEqual(wiki.git(sub, 'status', '--porcelain', '--untracked-files=all'), '')
        result = self.cli('pin', target, root=project, expected=2)
        self.assertIn('overwritten', result.stderr)
        self.assertEqual(wiki.git(sub, 'rev-parse', 'HEAD'), ignored_base)
        self.assertEqual(wiki.git(project, 'rev-parse', 'HEAD'), project_head)
        self.assertEqual(before, self.snapshot(sub))
        self.assertEqual(note.read_bytes(), b'ONLY COPY OF LOCAL USER NOTES\n')
        self.assertEqual(wiki.git(project, 'status', '--porcelain'), '')

    def test_pin_rejects_missing_abbreviated_blob_and_tag_objects(self):
        project, sub = self.project()
        wiki.git(sub, '-c', 'user.name=Local Fixture', '-c', 'user.email=fixture@example.invalid',
                 'tag', '-a', 'fixture-tag', '-m', 'Annotated tag')
        tag_object = wiki.git(sub, 'rev-parse', 'fixture-tag')
        blob_object = wiki.git(sub, 'rev-parse', 'HEAD:wiki/index.md')
        before = self.snapshot(sub)
        for revision in ('f' * 40, self.base[:12], 'HEAD', blob_object, tag_object):
            with self.subTest(revision=revision):
                self.cli('pin', revision, root=project, expected=2)
                self.assertEqual(wiki.git(sub, 'rev-parse', 'HEAD'), self.base)
                self.assertEqual(before, self.snapshot(sub))
                self.assertEqual(wiki.git(project, 'status', '--porcelain'), '')

    def test_pin_rejects_dirty_and_detached_project(self):
        project, sub = self.project()
        note = project / 'draft.txt'
        note.write_text('preserve')
        self.cli('pin', self.base, root=project, expected=2)
        self.assertEqual(note.read_text(), 'preserve')
        demo.commit(project, 'Preserve project note')
        wiki.git(project, 'checkout', '--detach', 'HEAD')
        self.cli('pin', self.base, root=project, expected=2)
        self.assertEqual(wiki.git(sub, 'rev-parse', 'HEAD'), self.base)
        self.assertEqual(note.read_text(), 'preserve')

    def test_writer_lock_blocks_cli_mutations_without_stealing_lock(self):
        before = self.snapshot()
        lock = Path(wiki.git(self.root, 'rev-parse', '--path-format=absolute', '--git-path', 'wiki-write.lock'))
        commands = (
            ('record', 'ingest', 'must not append'),
            ('index',),
            ('query', 'queue', '--version', 'FixtureQueue/1', '--record'),
            ('lint', '--base', self.base, '--record'),
            ('worktree', self.sandbox / 'blocked-worktree', 'contrib/blocked'),
        )
        with wiki.mutation_lock(self.root):
            original_lock = lock.read_bytes()
            for command in commands:
                with self.subTest(command=command[0]):
                    result = self.cli(*command, expected=2)
                    self.assertIn('writer or stale lock', result.stderr)
                    self.assertEqual(before, self.snapshot())
                    self.assertEqual(lock.read_bytes(), original_lock)
            self.cli('query', 'queue', '--version', 'FixtureQueue/1')
        self.assertFalse(lock.exists())
        self.assertFalse((self.sandbox / 'blocked-worktree').exists())
        self.cli('record', 'maintain', 'Lock released normally')
        self.assertNotEqual(before['wiki/log.md'], (self.root / 'wiki/log.md').read_bytes())

    def test_pin_obeys_project_and_submodule_writer_locks(self):
        project, sub = self.project()
        before = self.snapshot(sub)
        for locked in (project, sub):
            with self.subTest(locked=locked.name):
                with wiki.mutation_lock(locked):
                    self.cli('pin', self.base, root=project, expected=2)
                    self.assertEqual(wiki.git(sub, 'rev-parse', 'HEAD'), self.base)
                    self.assertEqual(before, self.snapshot(sub))
        self.cli('pin', self.base, root=project)

    def test_history_preserves_unicode_and_control_character_source_paths(self):
        raw = (self.root / 'raw/fixture-v1.md').read_bytes()
        names = ('nguồn.md', 'space name.md', 'tab\tname.md', 'line\nname.md')
        for name in names:
            (self.root / 'raw' / name).write_bytes(raw)
        baseline = demo.commit(self.root, 'Archive valid unusual source paths')
        self.assertEqual(wiki.lint(self.root, baseline)['errors'], [])
        source = self.root / 'raw/nguồn.md'
        source.write_bytes(raw + b'Changed historical evidence\n')
        self.assertIn('Immutable source changed: raw/nguồn.md', wiki.lint(self.root, baseline)['errors'])


if __name__ == '__main__':
    unittest.main()
