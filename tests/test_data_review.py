"""Regression coverage for independently reproduced data-boundary defects."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import demo
import fixtures
import wiki


class DataReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = (Path(self.temp.name) / 'repo').resolve()
        self.root.mkdir()
        wiki.git(self.root, 'init', '-b', 'contrib/data-review')
        fixtures.seed(self.root)
        self.base = demo.commit(self.root, 'Data review baseline')
        self.page = self.root / 'wiki/concepts/queue.md'
        self.metadata, self.body = wiki.read_page(self.page)
        self.cli = Path(wiki.__file__).resolve()

    def errors(self):
        return '\n'.join(wiki.lint(self.root, self.base)['errors'])

    def write_page(self, metadata=None, body=None):
        fixtures.write(self.page, metadata if metadata is not None else self.metadata,
                       body if body is not None else self.body)

    def assert_symlink_readers_blocked(self):
        old_index = (self.root / 'wiki/index.md').read_bytes()
        old_log = (self.root / 'wiki/log.md').read_bytes()
        self.assertIn('symlink', self.errors())
        with self.assertRaisesRegex(ValueError, 'symlink'):
            wiki.query(self.root, 'queue', 'FixtureQueue/1')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            wiki.index_text(self.root)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            wiki.update_index(self.root)
        self.assertEqual((self.root / 'wiki/index.md').read_bytes(), old_index)
        self.assertEqual((self.root / 'wiki/log.md').read_bytes(), old_log)

    def test_external_symlink_cannot_expose_private_claim(self):
        private = copy.deepcopy(self.metadata)
        private['scope'] = 'project'
        private['claims'][0]['text'] = 'PRIVATE OUTSIDE REPOSITORY'
        target = self.root.parent / 'private.md'
        fixtures.write(target, private, self.body)
        (self.root / 'wiki/concepts/escape.md').symlink_to(target)
        self.assert_symlink_readers_blocked()
        run = subprocess.run([sys.executable, str(self.cli), '--root', str(self.root),
                              'query', 'queue', '--version', 'FixtureQueue/1'],
                             capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn('PRIVATE OUTSIDE REPOSITORY', run.stdout)

    def test_internal_file_symlink_is_not_a_supported_page(self):
        (self.root / 'wiki/concepts/alias.md').symlink_to(self.page)
        self.assert_symlink_readers_blocked()

    def test_symlink_ancestor_inside_and_outside_repository(self):
        outside = self.root.parent / 'outside'
        outside.mkdir()
        fixtures.write(outside / 'private.md', self.metadata, self.body)
        alias = self.root / 'wiki/alias'
        for target in (self.root / 'wiki/concepts', outside):
            with self.subTest(target=str(target)):
                alias.symlink_to(target, target_is_directory=True)
                try:
                    self.assert_symlink_readers_blocked()
                    with self.assertRaisesRegex(ValueError, 'symlink'):
                        wiki.inside(self.root, 'wiki/alias/queue.md')
                finally:
                    alias.unlink()

    def test_raw_directory_symlink_is_rejected(self):
        alias = self.root / 'raw/alias'
        alias.symlink_to(self.root / 'wiki/concepts', target_is_directory=True)
        self.assertIn('symlink', self.errors())
        with self.assertRaisesRegex(ValueError, 'symlink'):
            wiki.metadata_path(self.root, 'raw/alias/queue.md', 'raw')

    def test_raw_dotdot_citation_cannot_bypass_immutable_archive(self):
        mutable = self.root / 'docs/mutable.md'
        mutable.parent.mkdir()
        mutable.write_bytes((self.root / 'raw/fixture-v1.md').read_bytes())
        self.metadata['sources'] = ['raw/../docs/mutable.md']
        self.metadata['claims'][0]['sources'] = self.metadata['sources'][:]
        self.write_page()
        baseline = demo.commit(self.root, 'Traversal reproduction')
        self.assertIn('canonical', '\n'.join(wiki.lint(self.root, baseline)['errors']))
        with mutable.open('a', encoding='utf-8') as stream:
            stream.write('\nA mutable source rewrite.\n')
        self.assertIn('canonical', '\n'.join(wiki.lint(self.root, baseline)['errors']))
        with self.assertRaisesRegex(ValueError, 'canonical'):
            wiki.query(self.root, 'queue', 'FixtureQueue/1')

    def test_nested_reserved_filenames_receive_scope_validation(self):
        for name in ('index.md', 'log.md'):
            with self.subTest(name=name):
                path = self.root / 'wiki/project' / name
                metadata = copy.deepcopy(self.metadata)
                metadata.update(id='private-' + name, scope='project')
                fixtures.write(path, metadata, '# Private data\n[Related](../concepts/queue.md)\n')
                try:
                    self.assertIn('Project/session', self.errors())
                    with self.assertRaisesRegex(ValueError, 'Project/session'):
                        wiki.query(self.root, 'queue', 'FixtureQueue/1')
                finally:
                    path.unlink()

    def test_valid_nested_index_and_log_are_regular_knowledge_pages(self):
        for name in ('index.md', 'log.md'):
            metadata = copy.deepcopy(self.metadata)
            metadata.update(id='nested-' + name, title='Nested ' + name)
            fixtures.write(self.root / 'wiki/nested' / name, metadata,
                           '# Nested page\n[Related](../concepts/queue.md)\n')
        wiki.update_index(self.root)
        self.assertEqual(self.errors(), '')
        paths = {p.relative_to(self.root).as_posix() for p in wiki.pages(self.root)}
        self.assertIn('wiki/nested/index.md', paths)
        self.assertIn('wiki/nested/log.md', paths)

    def test_invalid_appended_log_events_are_rejected_without_rewriting(self):
        log = self.root / 'wiki/log.md'
        original = log.read_bytes()
        invalid = (
            '<<<<<<< branch\n=======\n>>>>>>> other\n',
            '- not-json\n',
            '- {"at":"2026-10-15T00:00:00+00:00","operation":"delete","detail":"bad"}\n',
            '- {"at":"2026-10-15T00:00:00","operation":"ingest","detail":"bad"}\n',
            '- {"at":false,"operation":"ingest","detail":"bad"}\n',
            '- {"at":"2026-10-15T00:00:00+00:00","operation":"ingest"}\n',
            '- {"at":"2026-10-15T00:00:00+00:00","operation":"ingest","detail":NaN}\n',
        )
        for appended in invalid:
            with self.subTest(appended=appended):
                damaged = original + appended.encode('utf-8')
                log.write_bytes(damaged)
                self.assertTrue(wiki.lint(self.root, self.base)['errors'])
                with self.assertRaises(ValueError):
                    wiki.record(self.root, 'ingest', 'must not extend invalid log')
                self.assertEqual(log.read_bytes(), damaged)
        log.write_bytes(original)
        self.assertEqual(self.errors(), '')

    def test_synthetic_sources_require_explicit_fixture_provenance(self):
        for value in (None, False, 'true'):
            with self.subTest(value=value):
                metadata = copy.deepcopy(self.metadata)
                if value is None:
                    metadata.pop('fixture')
                else:
                    metadata['fixture'] = value
                self.write_page(metadata)
                self.assertIn('fixture', self.errors())
                with self.assertRaisesRegex(ValueError, 'fixture'):
                    wiki.query(self.root, 'queue', 'FixtureQueue/1')
        self.write_page()
        self.assertTrue(wiki.query(self.root, 'queue', 'FixtureQueue/1')[0]['fixture'])

    def test_fixture_cannot_be_promoted_to_verified(self):
        proof = self.root / 'docs/proof.md'
        proof.parent.mkdir()
        proof.write_text('Synthetic review only; not production verification.\n', encoding='utf-8')
        self.metadata.update(status='verified', review_record='docs/proof.md',
                             verification_evidence='docs/proof.md',
                             verified_at=self.metadata['updated_at'])
        self.write_page()
        (self.root / 'wiki/index.md').write_text(wiki.index_text(self.root), encoding='utf-8')
        self.assertIn('cannot be verified', self.errors())

    def test_search_matches_claim_text_and_preserves_version_scope(self):
        fixtures.seed(self.root, 2)
        metadata, body = wiki.read_page(self.page)
        metadata['claims'][0]['text'] = 'Oldcapacitytoken is eight.'
        metadata['claims'][1]['text'] = 'Backpressuretoken changes capacity to sixteen.'
        self.write_page(metadata, body)
        self.assertEqual(self.errors(), '')
        found = wiki.query(self.root, 'backpressuretoken', 'FixtureQueue/2')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['claims'][0]['sources'], ['raw/fixture-v2.md'])
        self.assertEqual(wiki.query(self.root, 'Backpressuretoken', 'FixtureQueue/1'), [])
        self.assertEqual(wiki.query(self.root, 'Oldcapacitytoken', 'FixtureQueue/2'), [])

    def test_duplicate_json_keys_are_rejected_in_pages_and_logs(self):
        original_page = self.page.read_text(encoding='utf-8')
        self.page.write_text(original_page.replace('"scope": "shared"',
                                                  '"scope": "project", "scope": "shared"'), encoding='utf-8')
        self.assertIn('Duplicate JSON key', self.errors())
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            wiki.query(self.root, 'queue', 'FixtureQueue/1')
        self.page.write_text(original_page, encoding='utf-8')
        with (self.root / 'wiki/log.md').open('a', encoding='utf-8') as stream:
            stream.write('- {"at":"2026-10-15T00:00:00+00:00","operation":"review",'
                         '"operation":"ingest","detail":"ambiguous"}\n')
        self.assertIn('Duplicate JSON key', self.errors())

    def test_malformed_metadata_cli_returns_error_without_traceback(self):
        cases = (
            ('claim-kind', lambda m: m['claims'][0].update(kind=[])),
            ('claim-versions', lambda m: m['claims'][0].update(applies_to=[{}])),
            ('claim-sources', lambda m: m['claims'][0].update(sources=[{}])),
            ('review-record', lambda m: m.update(review_record=[])),
            ('contradiction-status', lambda m: m.update(contradictions=[{
                'status': {}, 'sources': ['raw/fixture-v1.md'], 'resolution': 'pending'}])),
            ('title', lambda m: m.update(title=[])),
        )
        for name, change in cases:
            with self.subTest(name=name):
                metadata = copy.deepcopy(self.metadata)
                change(metadata)
                self.write_page(metadata)
                for command in (['lint', '--base', self.base],
                                ['query', 'queue', '--version', 'FixtureQueue/1']):
                    run = subprocess.run([sys.executable, str(self.cli), '--root', str(self.root), *command],
                                         capture_output=True, text=True)
                    self.assertNotEqual(run.returncode, 0)
                    self.assertNotIn('Traceback', run.stdout + run.stderr)

    def test_unicode_source_paths_are_included_in_immutable_baseline(self):
        name = 'raw/nguồn xác minh.md'
        source = self.root / name
        source.write_bytes((self.root / 'raw/fixture-v1.md').read_bytes())
        self.metadata['sources'] = [name]
        self.metadata['claims'][0]['sources'] = [name]
        self.write_page()
        baseline = demo.commit(self.root, 'Unicode archived source')
        self.assertEqual(wiki.lint(self.root, baseline)['errors'], [])
        with source.open('a', encoding='utf-8') as stream:
            stream.write('\nNguồn cũ bị thay đổi.\n')
        result = wiki.lint(self.root, baseline)
        self.assertIn('Immutable source changed: ' + name, result['errors'])
        self.assertFalse(result['history_checked'])


if __name__ == '__main__':
    unittest.main()
