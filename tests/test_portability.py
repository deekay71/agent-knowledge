"""Regressions for review findings: local dates ahead of UTC, OS metadata files,
Windows line-ending conversion and query ranking."""
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import demo
import export_vault
import fixtures
import git_hooks
import wiki


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sandbox = Path(self.temp.name).resolve()
        self.root = self.sandbox / 'repo'
        self.root.mkdir()
        wiki.git(self.root, 'init', '-b', 'contrib/portability')
        fixtures.seed(self.root)
        self.base = demo.commit(self.root, 'Baseline')
        self.page = self.root / 'wiki/concepts/queue.md'

    def set_meta(self, path, **values):
        meta, body = wiki.read_page(path)
        meta.update(values)
        fixtures.write(path, meta, body)

    def utc_today(self):
        return dt.datetime.now(dt.timezone.utc).date()

    # Local calendar dates ------------------------------------------------------------

    def test_local_date_one_day_ahead_of_utc_is_accepted(self):
        # 00:00-06:59 in UTC+7 is still the previous day in UTC.
        tomorrow = (self.utc_today() + dt.timedelta(days=1)).isoformat()
        self.set_meta(self.page, updated_at=tomorrow)
        result = wiki.lint(self.root, self.base)
        self.assertEqual(result['errors'], [])
        self.assertEqual(wiki.query(self.root, 'queue', 'FixtureQueue/1')[0]['page'], 'wiki/concepts/queue.md')

    def test_dates_beyond_any_time_zone_are_still_future(self):
        too_far = (self.utc_today() + dt.timedelta(days=2)).isoformat()
        with self.assertRaisesRegex(ValueError, 'Future date'):
            wiki.date(too_far, 'updated_at')
        self.set_meta(self.page, updated_at=too_far)
        self.assertIn('Future date', '\n'.join(wiki.lint(self.root)['errors']))

    # OS metadata files -----------------------------------------------------------------

    def write_os_metadata(self):
        for name in ('wiki/.DS_Store', 'raw/.DS_Store', 'wiki/concepts/._queue.md',
                     'raw/Thumbs.db', 'wiki/lessons/desktop.ini'):
            (self.root / name).write_bytes(b'\x00\x00\x00\x01Bud1 metadata')

    def test_os_metadata_files_do_not_block_lint_query_or_index(self):
        before = wiki.index_text(self.root)
        self.write_os_metadata()
        self.assertEqual(wiki.lint(self.root, self.base)['errors'], [])
        self.assertEqual(wiki.query(self.root, 'queue', 'FixtureQueue/1')[0]['page'], 'wiki/concepts/queue.md')
        self.assertEqual(wiki.index_text(self.root), before)

    def test_other_unsupported_files_and_metadata_symlinks_still_fail(self):
        (self.root / 'wiki/notes.txt').write_text('not knowledge')
        self.assertIn('Only regular Markdown', '\n'.join(wiki.lint(self.root)['errors']))
        (self.root / 'wiki/notes.txt').unlink()
        outside = self.sandbox / 'private.md'
        outside.write_text('private data')
        (self.root / 'wiki/.DS_Store').symlink_to(outside)
        self.assertIn('symlink', '\n'.join(wiki.lint(self.root)['errors']))

    def test_vault_check_and_refresh_ignore_os_metadata(self):
        output = self.root / 'vault'
        export_vault.export(self.root, output)
        (output / '.DS_Store').write_bytes(b'Bud1')
        (output / 'wiki/._index.md').write_bytes(b'AppleDouble')
        self.assertEqual(export_vault.check(self.root, output)['files'], 8)
        self.set_meta(self.page, summary='Changed summary for refresh.')
        (self.root / 'wiki/index.md').write_text(wiki.index_text(self.root))
        export_vault.export(self.root, output, refresh=True)
        export_vault.check(self.root, output)
        self.assertEqual((output / '.DS_Store').read_bytes(), b'Bud1')

    def test_git_hook_refuses_staged_os_metadata(self):
        (self.root / 'wiki/.DS_Store').write_bytes(b'Bud1')
        wiki.git(self.root, 'add', '--force', 'wiki/.DS_Store')
        with self.assertRaisesRegex(ValueError, 'OS metadata file staged'):
            git_hooks.check(self.root)

    # Line endings ----------------------------------------------------------------------

    def autocrlf_clone(self, source, name):
        clone = self.sandbox / name
        subprocess.run(['git', 'clone', '-q', '-c', 'core.autocrlf=true', str(source), str(clone)],
                       check=True, capture_output=True)
        return clone

    def test_autocrlf_checkout_keeps_lf_with_repository_attributes(self):
        control = self.autocrlf_clone(self.root, 'without-attributes')
        # Proves this Git converts on checkout, so the next assertion is meaningful.
        self.assertIn(b'\r\n', (control / 'wiki/log.md').read_bytes())
        self.assertIn('Invalid log header', '\n'.join(wiki.lint(control)['errors']))

        shutil.copy2(REPO / '.gitattributes', self.root / '.gitattributes')
        base = demo.commit(self.root, 'Add line-ending attributes')
        clone = self.autocrlf_clone(self.root, 'with-attributes')
        for name in ('wiki/log.md', 'wiki/index.md', 'wiki/concepts/queue.md', 'raw/fixture-v1.md'):
            self.assertNotIn(b'\r\n', (clone / name).read_bytes(), name)
        result = wiki.lint(clone, base)
        self.assertEqual(result['errors'], [])
        self.assertTrue(result['history_checked'])

    def test_archived_sources_keep_their_exact_bytes(self):
        shutil.copy2(REPO / '.gitattributes', self.root / '.gitattributes')
        raw = self.root / 'raw/crlf-source.md'
        raw.write_bytes(b'---json\r\n{"origin": "synthetic:crlf", "collected_at": "2026-10-15", '
                        b'"scope": "shared", "version": "FixtureQueue/1", "permission": "synthetic-fixture"}'
                        b'\r\n---\r\n# CRLF source\r\nAuthored on Windows.\r\n')
        base = demo.commit(self.root, 'Archive a CRLF source')
        self.assertEqual(wiki.git_bytes(self.root, 'show', 'HEAD:raw/crlf-source.md'), raw.read_bytes())
        self.assertEqual(wiki.lint(self.root, base)['errors'], [])


class QueryRankingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = (Path(self.temp.name) / 'repo').resolve()
        self.root.mkdir()
        wiki.git(self.root, 'init', '-b', 'contrib/query')
        fixtures.seed(self.root)
        template = (self.root / 'wiki/concepts/queue.md').read_text()
        # Five pages that only mention the term, sorting before the page that is about it.
        # The term "backlog" appears nowhere in the seeded fixture pages.
        for number in range(5):
            self.add_page(template, f'a{number}', f'filler-{number}', f'Filler {number}',
                          'Mentions a backlog in passing.', ['fixture'])
        self.add_page(template, 'zz-backlog-guide', 'backlog-guide', 'Backlog guide',
                      'Everything about the backlog.', ['fixture', 'backlog'])
        (self.root / 'wiki/index.md').write_text(wiki.index_text(self.root))
        self.assertEqual(wiki.lint(self.root)['errors'], [])

    def add_page(self, template, name, page_id, title, summary, tags):
        path = self.root / f'wiki/concepts/{name}.md'
        path.write_text(template)
        meta, body = wiki.read_page(path)
        meta.update(id=page_id, title=title, summary=summary, tags=tags)
        fixtures.write(path, meta, body)

    def pages(self, *args, **kwargs):
        return [hit['page'] for hit in wiki.query(self.root, *args, **kwargs)]

    def test_title_match_ranks_first_even_when_it_sorts_last(self):
        pages = self.pages('backlog', 'FixtureQueue/1')
        self.assertEqual(pages, ['wiki/concepts/zz-backlog-guide.md'] + [f'wiki/concepts/a{n}.md' for n in range(4)])

    def test_ties_keep_deterministic_path_order(self):
        pages = self.pages('passing', 'FixtureQueue/1')
        self.assertEqual(pages, [f'wiki/concepts/a{n}.md' for n in range(5)])

    def test_words_may_appear_in_any_order_but_all_must_match(self):
        self.assertEqual(self.pages('guide backlog', 'FixtureQueue/1'), ['wiki/concepts/zz-backlog-guide.md'])
        self.assertEqual(self.pages('backlog nonexistentword', 'FixtureQueue/1'), [])

    def test_limit_is_configurable_and_validated(self):
        self.assertEqual(len(self.pages('backlog', 'FixtureQueue/1', limit=10)), 6)
        self.assertEqual(len(self.pages('backlog', 'FixtureQueue/1', limit=2)), 2)
        for bad in (0, -1, True, '3'):
            with self.subTest(limit=bad), self.assertRaisesRegex(ValueError, 'limit'):
                wiki.query(self.root, 'backlog', 'FixtureQueue/1', limit=bad)
        cli = [sys.executable, str(REPO / 'scripts/wiki.py'), '--root', str(self.root), 'query', 'backlog',
               '--version', 'FixtureQueue/1']
        ok = subprocess.run(cli + ['--limit', '1'], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual([hit['page'] for hit in json.loads(ok.stdout)], ['wiki/concepts/zz-backlog-guide.md'])
        bad = subprocess.run(cli + ['--limit', '0'], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertIn('limit', bad.stderr)
        self.assertNotIn('Traceback', bad.stderr)

    def test_version_scope_still_filters_before_ranking(self):
        self.assertEqual(self.pages('backlog', 'FixtureQueue/2'), [])


if __name__ == '__main__':
    unittest.main()
