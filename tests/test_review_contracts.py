import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import demo
import fixtures
import wiki


class ReviewContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'repo';self.root.mkdir()
        wiki.git(self.root,'init','-b','contrib/test');fixtures.seed(self.root)
        self.base=demo.commit(self.root,'baseline')

    def mutate(self, fn):
        p=self.root/'wiki/concepts/queue.md';m,b=wiki.read_page(p);fn(m);fixtures.write(p,m,b)

    def test_metadata_and_escaped_brackets_not_links(self):
        self.mutate(lambda m:m.update(summary='Meaning of [brackets](in-code.md)'))
        p=self.root/'wiki/concepts/queue.md'
        with p.open('a') as f:f.write('\nLiteral \\[not a link](missing.md)\n')
        wiki.update_index(self.root)
        self.assertEqual(wiki.lint(self.root,self.base)['errors'],[])

    def test_unreadable_raw_directory_fails_closed(self):
        folder=self.root/'raw/denied';folder.mkdir()
        (folder/'private.md').write_text('not valid, not authorized')
        folder.chmod(0)
        try:
            self.assertTrue(wiki.lint(self.root)['errors'])
        finally:
            folder.chmod(0o700)

    def test_unicode_log_separators_and_markdown_are_data(self):
        for sep in ('\u0085', '\u2028', '\u2029'):
            wiki.record(self.root,'query','before'+sep+'after [literal](missing.md)')
        self.assertEqual(wiki.lint(self.root,self.base)['errors'],[])

    def test_synthesized_merge_markers_rejected(self):
        p=self.root/'wiki/concepts/queue.md'
        with p.open('a') as f:f.write('\n<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> contrib/topic\n')
        self.assertIn('merge conflict markers',str(wiki.lint(self.root,self.base)['errors']))
        with self.assertRaises(ValueError):wiki.query(self.root,'queue','FixtureQueue/1')

    def test_raw_literal_merge_example_allowed(self):
        fixtures.write(self.root/'raw/example.md',dict(origin='synthetic:merge',collected_at='2026-10-15',scope='shared',version='Example/1',permission='synthetic-fixture'),'# Literal example\n<<<<<<< HEAD\nThis is quoted source data.\n')
        self.assertEqual(wiki.lint(self.root,self.base)['errors'],[])

    def test_verification_cannot_predate_updated_content(self):
        p=self.root/'raw/fixture-v1.md';m,b=wiki.read_page(p);m['permission']='approved';fixtures.write(p,m,b)
        (self.root/'review.md').write_text('Review evidence placeholder for structural test only.\n')
        self.mutate(lambda m:m.update(fixture=False,status='verified',review_record='review.md',verification_evidence='review.md',verified_at='2020-01-01'))
        self.assertIn('Verification must cover',str(wiki.lint(self.root)['errors']))
        self.assertTrue(any('stale verification' in w for w in wiki.lint(self.root)['warnings']))

    def test_synthetic_never_verified(self):
        (self.root/'review.md').write_text('Fake fixture record.\n')
        self.mutate(lambda m:m.update(status='verified',review_record='review.md',verification_evidence='review.md',verified_at=m['updated_at']))
        self.assertIn('cannot be verified',str(wiki.lint(self.root)['errors']))

    def test_self_replacement_rejected(self):
        self.mutate(lambda m:m.update(status='superseded',superseded_by='wiki/concepts/queue.md'))
        self.assertIn('another knowledge page',str(wiki.lint(self.root)['errors']))

    def test_replacement_cycle_rejected(self):
        self.mutate(lambda m:m.update(status='superseded',superseded_by='wiki/lessons/versioning.md'))
        p=self.root/'wiki/lessons/versioning.md';m,b=wiki.read_page(p)
        m.update(status='superseded',superseded_by='wiki/concepts/queue.md');fixtures.write(p,m,b)
        self.assertIn('replacement cycle',str(wiki.lint(self.root)['errors']))

    def test_warning_for_no_baseline(self):
        result=wiki.lint(self.root)
        self.assertFalse(result['history_checked'])
        self.assertTrue(any('History not checked' in w for w in result['warnings']))
        self.assertFalse(wiki.lint(self.root,'not-a-ref')['history_checked'])

    def test_missing_layout_not_valid_empty_wiki(self):
        root=Path(self.temp.name)/'empty';root.mkdir()
        self.assertIn('Missing directory',str(wiki.lint(root)['errors']))

    def test_unsupported_file_is_not_silent(self):
        (self.root/'wiki/private.txt').write_text('not supported')
        self.assertIn('Only regular Markdown',str(wiki.lint(self.root)['errors']))

    def test_index_and_log_rollback_on_second_write_failure(self):
        self.mutate(lambda m:m.update(summary='Changed summary'))
        old_index=(self.root/'wiki/index.md').read_bytes();old_log=(self.root/'wiki/log.md').read_bytes()
        original=wiki.atomic_write
        def fail_log(path,data):
            if path.name=='log.md':raise PermissionError('synthetic failure before log replacement')
            original(path,data)
        with patch.object(wiki,'atomic_write',side_effect=fail_log):
            with self.assertRaises(PermissionError):wiki.update_index(self.root)
        self.assertEqual((self.root/'wiki/index.md').read_bytes(),old_index)
        self.assertEqual((self.root/'wiki/log.md').read_bytes(),old_log)

    def test_index_preflight_does_not_mutate_bad_log(self):
        self.mutate(lambda m:m.update(summary='Changed summary'))
        (self.root/'wiki/log.md').write_text('# Wiki log\ninvalid\n')
        old=(self.root/'wiki/index.md').read_bytes()
        with self.assertRaises(ValueError):wiki.update_index(self.root)
        self.assertEqual((self.root/'wiki/index.md').read_bytes(),old)

    def test_non_contribution_branch_blocked(self):
        wiki.git(self.root,'switch','-c','release')
        with self.assertRaises(ValueError):wiki.record(self.root,'review','do not write')

    def test_unicode_index_link_roundtrip(self):
        p=self.root/'wiki/concepts/queue.md';p.rename(p.with_name('hàng đợi.md'))
        lesson=self.root/'wiki/lessons/versioning.md'
        lesson.write_text(lesson.read_text().replace('../concepts/queue.md','../concepts/hàng đợi.md'))
        wiki.update_index(self.root)
        self.assertEqual(wiki.lint(self.root,self.base)['errors'],[])
