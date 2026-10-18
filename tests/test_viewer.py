"""Graph schema, confined source reads and real loopback HTTP regressions."""
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import demo
import fixtures
import viewer
import wiki


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wiki viewer ')
        self.addCleanup(self.temp.cleanup)
        self.sandbox = Path(self.temp.name).resolve()
        self.root = self.sandbox / 'repo with spaces'
        self.root.mkdir()
        wiki.git(self.root, 'init', '-b', 'contrib/viewer-test')
        fixtures.seed(self.root)
        self.base = demo.commit(self.root, 'Fixture baseline')

    def mutate(self, change, body_add=''):
        path = self.root / 'wiki/concepts/queue.md'
        meta, body = wiki.read_page(path)
        change(meta)
        fixtures.write(path, meta, body + body_add)
        (self.root / 'wiki/index.md').write_text(wiki.index_text(self.root))

    def graph(self):
        return viewer.build_graph(self.root)

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*')
                if p.is_file() and '.git' not in p.relative_to(self.root).parts}

    def test_canonical_graph_has_stable_node_edge_ids_and_real_snapshot_metadata(self):
        first, second = self.graph(), self.graph()
        self.assertEqual(first['format'], 1)
        self.assertEqual(first['stats'], {'nodes': 4, 'edges': 9})
        self.assertEqual(first['source_digest'], second['source_digest'])
        self.assertEqual(first['nodes'], second['nodes'])
        self.assertEqual(first['edges'], second['edges'])
        self.assertEqual(first['diagnostics'], [])
        self.assertEqual(first['diagnostic_summary'], {'total': 0, 'by_code': {}, 'by_severity': {}})
        self.assertEqual(first['snapshot']['revision'], self.base)
        self.assertTrue(first['snapshot']['loaded_at'])
        self.assertTrue(first['snapshot']['index_updated_at'])
        kinds = {node['kind'] for node in first['nodes']}
        self.assertEqual(kinds, {'source', 'concept', 'lesson', 'navigation'})
        for node in first['nodes']:
            self.assertNotIn('---json', node['body'])
            self.assertIsInstance(node['metadata'], dict)
            self.assertIsInstance(node['tags'], list)
            self.assertTrue(node['evidence_complete'])
            self.assertEqual(node['diagnostic_ids'], [])
        for edge in first['edges']:
            self.assertTrue(edge['explicit'])
            self.assertEqual(edge['provenance']['file'], edge['source'])
            self.assertTrue(edge['provenance']['section'])

    def test_log_docs_project_inbox_are_never_opened_or_exposed(self):
        original = self.graph()
        (self.root / 'wiki/log.md').unlink()
        private = self.sandbox / 'private.md'
        private.write_text('ABSOLUTELY_PRIVATE_SENTINEL\n')
        (self.root / 'wiki/log.md').symlink_to(private)
        for folder in ('docs', 'knowledge/project', 'knowledge/inbox'):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
            (self.root / folder / 'private.md').write_text('ABSOLUTELY_PRIVATE_SENTINEL\n')
        opened = []
        real = viewer.regular_bytes
        def capture(parent, name, limit):
            opened.append(name)
            return real(parent, name, limit)
        with mock.patch.object(viewer, 'regular_bytes', side_effect=capture):
            graph = self.graph()
        self.assertNotIn('log.md', opened)
        self.assertNotIn('private.md', opened)
        self.assertEqual(graph['source_digest'], original['source_digest'])
        self.assertNotIn('ABSOLUTELY_PRIVATE_SENTINEL', json.dumps(graph))

    def test_review_references_are_text_only_and_not_opened(self):
        self.mutate(lambda m: m.update(status='reviewed', review_record='docs/not-opened.md'))
        graph = self.graph()
        node = next(n for n in graph['nodes'] if n['kind'] == 'concept')
        self.assertEqual(node['metadata']['review_record'], 'docs/not-opened.md')
        self.assertFalse(any(n['id'].startswith('docs/') for n in graph['nodes']))
        self.assertIn('review files', str(graph['warnings']))

    def test_unsafe_metadata_references_fail_without_opening_outside(self):
        self.mutate(lambda m: m.update(status='reviewed', review_record='../PRIVATE_SECRET.md'))
        with self.assertRaises(viewer.ViewerError) as error:
            self.graph()
        self.assertNotIn('PRIVATE_SECRET', str(error.exception))
        self.assertNotIn(str(self.root), str(error.exception))

    def test_project_scope_fails_closed_for_unreferenced_raw(self):
        fixtures.write(self.root / 'raw/private.md', {'origin': 'SECRET_ORIGIN', 'collected_at': '2026-01-01',
                       'scope': 'project', 'version': 'Private/1', 'permission': 'approved'}, 'SECRET_BODY')
        with self.assertRaisesRegex(viewer.ViewerError, 'not cleared'):
            self.graph()

    def test_project_wiki_page_fails_closed(self):
        self.mutate(lambda m: m.update(scope='project'))
        with self.assertRaises(viewer.ViewerError):
            self.graph()

    def test_invalid_metadata_duplicate_keys_and_evidence_versions_rejected(self):
        path = self.root / 'wiki/concepts/queue.md'
        original = path.read_bytes()
        path.write_bytes(original.replace(b'"id":', b'"id":"duplicate", "id":', 1))
        with self.assertRaises(viewer.ViewerError):
            self.graph()
        path.write_bytes(original)
        self.mutate(lambda m: m['claims'][0].update(applies_to=['Wrong/999']))
        with self.assertRaises(viewer.ViewerError):
            self.graph()

    def test_synthetic_cannot_become_verified(self):
        self.mutate(lambda m: m.update(status='verified', verified_at=m['updated_at'], review_record='docs/review.md',
                                      verification_evidence='docs/evidence.md'))
        with self.assertRaises(viewer.ViewerError):
            self.graph()

    def test_index_drift_is_diagnostic_but_missing_index_fails_closed(self):
        path = self.root / 'wiki/index.md'
        path.write_text('PRIVATE_INDEX_CANARY\n[unvalidated link](concepts/queue.md)\n')
        graph = self.graph()
        diagnostic = next(d for d in graph['diagnostics'] if d['code'] == 'index_drift')
        self.assertEqual(diagnostic['source'], 'wiki/index.md')
        self.assertEqual(diagnostic['severity'], 'warning')
        self.assertEqual(graph['stats']['nodes'], 4)
        index = next(n for n in graph['nodes'] if n['kind'] == 'navigation')
        self.assertTrue(index['body_withheld'])
        self.assertIn('Viewer notice', index['body'])
        self.assertNotIn('PRIVATE_INDEX_CANARY', json.dumps(graph))
        self.assertFalse(any(e['source'] == 'wiki/index.md' for e in graph['edges']))
        path.unlink()
        with self.assertRaises(viewer.ViewerError) as error:
            self.graph()
        self.assertEqual(error.exception.code, 'missing_index')

    def test_index_with_private_or_malformed_frontmatter_is_fatal(self):
        for body in ('---json\n{"scope":"project","permission":"denied"}\n---\nPRIVATE_INDEX_CANARY',
                     '---\nscope: project\n---\nPRIVATE_INDEX_CANARY',
                     '+++\nscope="project"\n+++\nPRIVATE_INDEX_CANARY'):
            with self.subTest(body=body):
                (self.root / 'wiki/index.md').write_text(body)
                with self.assertRaises(viewer.ViewerError) as error:
                    self.graph()
                self.assertNotIn('PRIVATE_INDEX_CANARY', str(error.exception))

    def test_missing_sources_keep_claim_labels_without_dangling_edges_or_verification(self):
        (self.root / 'raw/fixture-v1.md').unlink()
        before = self.files()
        graph, again = self.graph(), self.graph()
        self.assertEqual(graph['diagnostics'], again['diagnostics'])
        self.assertEqual(graph['diagnostic_summary']['by_code']['missing_source'], 4)
        self.assertEqual(graph['diagnostic_summary']['by_code']['broken_link'], 1)
        eligible = {node['id'] for node in graph['nodes']}
        self.assertNotIn('raw/fixture-v1.md', eligible)
        self.assertTrue(all(edge['source'] in eligible and edge['target'] in eligible for edge in graph['edges']))
        for node in graph['nodes']:
            own = [d for d in graph['diagnostics'] if d['source'] == node['id']]
            self.assertEqual(set(node['diagnostic_ids']), {d['id'] for d in own})
            if node['kind'] in ('concept', 'lesson'):
                self.assertFalse(node['evidence_complete'])
                self.assertEqual(node['status'], 'draft')
        lesson = next(n for n in graph['nodes'] if n['kind'] == 'lesson')
        self.assertEqual(lesson['metadata']['claims'][0]['kind'], 'inference')
        for diagnostic in graph['diagnostics']:
            if diagnostic['code'] == 'missing_source':
                self.assertEqual(diagnostic['target'], 'raw/fixture-v1.md')
                self.assertIn('unverified', diagnostic['message'])
                self.assertEqual(diagnostic['provenance']['file'], diagnostic['source'])
        self.assertEqual(before, self.files())

    def test_missing_source_does_not_disable_known_claim_version_or_schema_checks(self):
        def add_missing(meta):
            meta['sources'].append('raw/missing.md')
            meta['applies_to'].append('Wrong/999')
            meta['claims'][0]['applies_to'] = ['Wrong/999']
        self.mutate(add_missing)
        with self.assertRaises(viewer.ViewerError):
            self.graph()
        self.mutate(lambda m: m['claims'][0].update(sources=['raw/missing.md']))
        graph = self.graph()
        self.assertFalse(next(n for n in graph['nodes'] if n['kind'] == 'concept')['evidence_complete'])
        self.mutate(lambda m: m['claims'][0].update(kind='fact'))
        with self.assertRaises(viewer.ViewerError):
            self.graph()

    def test_missing_metadata_source_must_be_a_canonical_raw_markdown_path(self):
        for target in ('docs/SECRET.md', 'raw/../SECRET.md', '/SECRET.md', 'raw/.git/SECRET.md', 'raw/SECRET.bin'):
            with self.subTest(target=target):
                self.mutate(lambda m: m.update(sources=['raw/fixture-v1.md', target]))
                with self.assertRaises(viewer.ViewerError) as error:
                    self.graph()
                self.assertNotIn('SECRET', str(error.exception))

    def test_broken_links_are_deduplicated_and_only_safe_eligible_paths_are_reported(self):
        additions = ('\n[missing](../concepts/absent.md)\n[duplicate](../concepts/absent.md#heading)\n'
                     '[encoded](../../raw/a%20missing.md)\n'
                     '[private](../../knowledge/project/SECRET.md)\n[log](../log.md)\n'
                     '[git](../../raw/.git/SECRET.md)\n[escape](../../../SECRET.md)\n'
                     '[url](https://example.invalid/SECRET.md)\n[js](javascript:SECRET)\n'
                     '[query](../concepts/absent.md?SECRET)\n'
                     '`[inline](../concepts/INLINE.md)`\n```md\n[fence](../concepts/FENCE.md)\n```\n')
        self.mutate(lambda m: None, additions)
        before = self.files()
        graph = self.graph()
        broken = [d for d in graph['diagnostics'] if d['code'] == 'broken_link']
        self.assertEqual({d['target'] for d in broken}, {'wiki/concepts/absent.md', 'raw/a missing.md'})
        self.assertEqual(len(broken), 2)
        self.assertNotIn('SECRET', json.dumps(graph['diagnostics']))
        self.assertTrue(all(node['evidence_complete'] for node in graph['nodes']))
        self.assertEqual(before, self.files())

    def test_orphan_excludes_index_source_and_self_links_but_accepts_other_page_inbound(self):
        original = self.root / 'wiki/concepts/queue.md'
        meta, _ = wiki.read_page(original)
        meta.update(id='orphan-page', title='Orphan fixture')
        path = self.root / 'wiki/concepts/orphan.md'
        fixtures.write(path, meta, '# Orphan\n[Self](orphan.md)\n')
        with (self.root / 'raw/fixture-v1.md').open('a') as handle:
            handle.write('\n[Raw backlink](../wiki/concepts/orphan.md)\n')
        (self.root / 'wiki/index.md').write_text(wiki.index_text(self.root))
        graph = self.graph()
        orphans = [d for d in graph['diagnostics'] if d['code'] == 'orphan_page']
        self.assertEqual([d['source'] for d in orphans], ['wiki/concepts/orphan.md'])
        self.assertEqual(orphans[0]['severity'], 'info')
        self.mutate(lambda m: None, '\n[Related page](orphan.md)\n')
        self.assertFalse(any(d['code'] == 'orphan_page' for d in self.graph()['diagnostics']))

    def test_diagnostic_limit_is_bounded_without_counting_repeated_links_twice(self):
        self.mutate(lambda m: None, '\n[missing](missing.md)\n' * 100)
        with mock.patch.object(viewer, 'MAX_DIAGNOSTICS', 1):
            self.assertEqual(self.graph()['diagnostic_summary']['total'], 1)
        self.mutate(lambda m: None, '\n[other](other.md)\n')
        with mock.patch.object(viewer, 'MAX_DIAGNOSTICS', 1):
            with self.assertRaises(viewer.ViewerError) as error:
                self.graph()
        self.assertEqual(error.exception.code, 'limit_exceeded')

    def test_diagnostics_do_not_allow_private_or_invalid_lineage_to_return_partial_graph(self):
        (self.root / 'raw/fixture-v1.md').unlink()
        fixtures.write(self.root / 'raw/private.md', {'origin': 'SECRET', 'collected_at': '2026-01-01',
                       'scope': 'project', 'version': 'Private/1', 'permission': 'approved'}, 'SECRET_BODY')
        with self.assertRaises(viewer.ViewerError) as error:
            self.graph()
        self.assertEqual(error.exception.code, 'private_scope')
        self.assertNotIn('SECRET', str(error.exception))
        (self.root / 'raw/private.md').unlink()
        self.mutate(lambda m: m.update(status='superseded', superseded_by='wiki/absent.md'))
        with self.assertRaises(viewer.ViewerError) as error:
            self.graph()
        self.assertEqual(error.exception.code, 'invalid_lineage')

    def test_symlink_file_directory_and_selected_root_rejected(self):
        outside = self.sandbox / 'outside'
        outside.mkdir()
        (outside / 'secret.md').write_text('SECRET_OUTSIDE')
        alias = self.sandbox / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(viewer.ViewerError):
            viewer.build_graph(alias)
        link = self.root / 'raw/leak.md'
        link.symlink_to(outside / 'secret.md')
        with self.assertRaises(viewer.ViewerError):
            self.graph()
        link.unlink()
        directory = self.root / 'wiki/leak'
        directory.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(viewer.ViewerError):
            self.graph()

    def test_symlink_swap_between_lstat_and_read_cannot_escape(self):
        source = self.root / 'raw/fixture-v1.md'
        secret = self.sandbox / 'secret.md'
        secret.write_text('SECRET_OUTSIDE')
        original = viewer.regular_bytes
        swapped = False
        def swap(parent, name, limit):
            nonlocal swapped
            if name == 'fixture-v1.md' and not swapped:
                source.unlink()
                source.symlink_to(secret)
                swapped = True
            return original(parent, name, limit)
        with mock.patch.object(viewer, 'regular_bytes', side_effect=swap):
            with self.assertRaises(viewer.ViewerError) as error:
                self.graph()
        self.assertTrue(swapped)
        self.assertNotIn('SECRET_OUTSIDE', str(error.exception))

    def test_fifo_and_nonmarkdown_files_rejected_without_blocking(self):
        pipe = self.root / 'raw/pipe.md'
        os.mkfifo(pipe)
        with self.assertRaises(viewer.ViewerError):
            self.graph()
        pipe.unlink()
        (self.root / 'raw/opaque.bin').write_bytes(b'private')
        with self.assertRaises(viewer.ViewerError):
            self.graph()

    def test_concurrent_edit_fails_without_partial_graph(self):
        original = viewer.scan
        count = 0
        def edit(fd):
            nonlocal count
            count += 1
            if count == 2:
                path = self.root / 'wiki/concepts/queue.md'
                path.write_text(path.read_text() + '\nConcurrent edit\n')
            return original(fd)
        with mock.patch.object(viewer, 'scan', side_effect=edit):
            with self.assertRaises(viewer.ViewerError) as error:
                self.graph()
        self.assertEqual(error.exception.code, 'concurrent_change')

    def test_resource_limits_are_enforced(self):
        for limit, value in [('MAX_FILE_BYTES', 32), ('MAX_TOTAL_BYTES', 100), ('MAX_NOTES', 2),
                             ('MAX_DIRECTORY_ENTRIES', 1), ('MAX_DEPTH', 0), ('MAX_EDGES', 2)]:
            with self.subTest(limit=limit), mock.patch.object(viewer, limit, value):
                with self.assertRaises(viewer.ViewerError) as error:
                    self.graph()
                self.assertEqual(error.exception.code, 'limit_exceeded')

    def test_external_js_absolute_and_private_links_never_add_edges(self):
        additions = ('\n[external](https://example.invalid/private.md)\n[js](javascript:alert(1))\n'
                     '[private](../../docs/private.md)\n[abs](/etc/passwd)\n'
                     '[encoded](%2e%2e/%2e%2e/docs/private.md)\n![image](../lessons/versioning.md)\n')
        before = self.graph()
        self.mutate(lambda m: None, additions)
        after = self.graph()
        self.assertEqual(before['edges'], after['edges'])
        self.assertNotEqual(before['source_digest'], after['source_digest'])

    def test_code_blocks_inline_code_and_anchors_do_not_create_edges(self):
        source = self.root / 'raw/fixture-v1.md'
        original = self.graph()
        with source.open('a') as handle:
            handle.write('\n```md\n[fence](../wiki/concepts/queue.md)\n```\n'
                         '\n~~~md\n[tilde](../wiki/concepts/queue.md)\n~~~\n'
                         '\n`[inline](../wiki/concepts/queue.md)`\n'
                         '\n    [indent](../wiki/concepts/queue.md)\n'
                         '\n[anchor](#local-heading)\n')
        self.assertEqual(self.graph()['edges'], original['edges'])
        with source.open('a') as handle:
            handle.write('\n[explicit](../wiki/concepts/queue.md)\n')
        after = self.graph()
        edges = [e for e in after['edges'] if e['source'] == 'raw/fixture-v1.md']
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]['kind'], 'link')

    def test_code_formatted_link_label_is_an_explicit_link(self):
        path = self.root / 'raw/fixture-v1.md'
        with path.open('a') as handle:
            handle.write('\nSee [`version lesson`](../wiki/lessons/versioning.md).\n'
                         '\n`[not a link](../wiki/concepts/queue.md)`\n')
        edges = [edge for edge in self.graph()['edges'] if edge['source'] == 'raw/fixture-v1.md']
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]['target'], 'wiki/lessons/versioning.md')

    def test_many_mixed_code_spans_and_real_links_preserve_exact_count(self):
        body = ('`[literal](hidden.md)` [`real`](visible.md)\n' * 5000)
        targets = list(viewer.prose_links(body))
        self.assertEqual(len(targets), 5000)
        self.assertEqual(set(targets), {'visible.md'})

    def test_raw_extras_cannot_claim_verification_or_hide_fixture_and_version(self):
        path = self.root / 'raw/fixture-v1.md'
        meta, body = wiki.read_page(path)
        meta.update(fixture=False, status='verified', applies_to={'invalid': 'FakeProduction/9'})
        fixtures.write(path, meta, body)
        node = next(node for node in self.graph()['nodes'] if node['kind'] == 'source')
        self.assertTrue(node['fixture'])
        self.assertEqual(node['status'], 'source')
        self.assertEqual(node['applies_to'], ['FixtureQueue/1'])

    def test_contradiction_claim_and_lineage_edges_have_real_provenance(self):
        fixtures.seed(self.root, 2)
        self.mutate(lambda m: m.update(supersedes=['wiki/lessons/versioning.md']))
        lesson = self.root / 'wiki/lessons/versioning.md'
        meta, body = wiki.read_page(lesson)
        meta.update(status='superseded', superseded_by='wiki/concepts/queue.md')
        fixtures.write(lesson, meta, body)
        (self.root / 'wiki/index.md').write_text(wiki.index_text(self.root))
        graph = self.graph()
        self.assertIn('contradiction', {e['kind'] for e in graph['edges']})
        for edge in graph['edges']:
            if edge['kind'] == 'contradiction':
                self.assertEqual(edge['status'], 'open')
                self.assertEqual(edge['provenance']['section'], 'metadata.contradictions[0].sources')
            if edge['kind'] == 'claim':
                self.assertIn(edge['claim_kind'], ('evidence', 'inference', 'unknown'))
        self.assertIn('supersedes', {e['kind'] for e in graph['edges']})
        self.assertIn('superseded_by', {e['kind'] for e in graph['edges']})
        self.assertTrue(any('contradiction' in w for w in graph['warnings']))

    def test_non_git_root_supported_and_build_never_writes_sources(self):
        plain = self.sandbox / 'plain'
        plain.mkdir()
        for folder in ('raw', 'wiki'):
            shutil.copytree(self.root / folder, plain / folder)
        before = self.files()
        graph = viewer.build_graph(plain)
        self.assertIsNone(graph['snapshot']['revision'])
        self.assertEqual(before, self.files())
        self.assertFalse((plain / '.git').exists())

    def test_revision_reads_only_in_root_head_refs_and_handles_packed_refs(self):
        wiki.git(self.root, 'pack-refs', '--all')
        opened = []
        real = viewer.regular_bytes
        def capture(parent, name, limit):
            opened.append(name)
            return real(parent, name, limit)
        with mock.patch.object(viewer, 'regular_bytes', side_effect=capture):
            self.assertEqual(self.graph()['snapshot']['revision'], self.base)
        self.assertIn('HEAD', opened)
        self.assertIn('packed-refs', opened)
        self.assertNotIn('config', opened)

    def test_external_gitfile_and_symlinked_refs_produce_null_revision(self):
        plain = self.sandbox / 'plain-gitfile'
        plain.mkdir()
        for folder in ('raw', 'wiki'):
            shutil.copytree(self.root / folder, plain / folder)
        (plain / '.git').write_text('gitdir: ' + str(self.root / '.git') + '\n')
        self.assertIsNone(viewer.build_graph(plain)['snapshot']['revision'])
        head = self.root / '.git/HEAD'
        head.write_text('ref: refs/heads/outside\n')
        (self.root / '.git/refs/heads/outside').symlink_to(self.root / '.git/refs/heads/contrib/viewer-test')
        self.assertIsNone(self.graph()['snapshot']['revision'])

    def test_cli_help_and_check_are_read_only_and_no_export_option(self):
        before = self.files()
        help_result = subprocess.run([sys.executable, str(SCRIPTS / 'viewer.py'), '--help'], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertNotIn('--export', help_result.stdout)
        checked = subprocess.run([sys.executable, str(SCRIPTS / 'viewer.py'), '--root', str(self.root), '--check'],
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        summary = json.loads(checked.stdout)
        self.assertEqual(summary['stats']['nodes'], 4)
        self.assertNotIn('nodes', summary)
        self.assertEqual(summary['diagnostic_summary']['total'], 0)
        self.assertEqual(self.files(), before)

    def test_cli_check_reports_diagnostic_errors_separately_from_fatal_validation(self):
        command = [sys.executable, str(SCRIPTS / 'viewer.py'), '--root', str(self.root), '--check']
        (self.root / 'raw/fixture-v1.md').unlink()
        checked = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(checked.returncode, 1, checked.stderr)
        summary = json.loads(checked.stdout)
        self.assertEqual(summary['diagnostic_summary']['by_severity']['error'], 4)
        self.assertNotIn('nodes', summary)
        self.mutate(lambda m: m.update(scope='project', title='PRIVATE_CLI_CANARY'))
        checked = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(checked.returncode, 2)
        self.assertEqual(checked.stdout, '')
        self.assertNotIn('PRIVATE_CLI_CANARY', checked.stderr)


# Give the HTTP suite only shared fixture helpers, not duplicate graph cases.
class ViewerHTTPTests(unittest.TestCase):
    setUp = ViewerTests.setUp
    files = ViewerTests.files
    mutate = ViewerTests.mutate

    def start(self):
        assets = self.sandbox / 'trusted-assets'
        self.temp_assets = assets
        assets.mkdir()
        for name, body in [('index.html', '<h1>trusted viewer</h1>'), ('app.js', 'window.trusted=true;'), ('style.css', 'body{}')]:
            (assets / name).write_text(body)
        (assets / 'vendor').mkdir()
        for name in ('cytoscape.min.js', 'markdown-it.min.js', 'purify.min.js'):
            (assets / 'vendor' / name).write_text('// trusted library fixture')
        patch = mock.patch.object(viewer, 'ASSET_ROOT', assets)
        patch.start()
        self.addCleanup(patch.stop)
        server = viewer.create_server(self.root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        self.server = server
        return server

    def request(self, path, method='GET', headers=None, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), data
        connection.close()
        return result

    def test_loopback_api_static_allowlist_and_security_headers(self):
        server = self.start()
        self.assertEqual(server.server_address[0], '127.0.0.1')
        before = self.files()
        for path in ('/', '/index.html', '/app.js', '/style.css', '/vendor/cytoscape.min.js', '/api/graph'):
            status, headers, data = self.request(path)
            self.assertEqual(status, 200, data)
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
            self.assertIn("style-src-attr 'unsafe-inline'", headers['Content-Security-Policy'])
            self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(before, self.files())

    def test_assets_are_not_served_from_selected_data_root(self):
        self.start()
        (self.root / 'viewer').mkdir()
        (self.root / 'viewer/app.js').write_text('SECRET_UNTRUSTED_CODE')
        status, _, body = self.request('/app.js')
        self.assertEqual(status, 200)
        self.assertIn(b'window.trusted=true', body)
        self.assertNotIn(b'SECRET_UNTRUSTED_CODE', body)

    def test_encoded_traversal_source_and_arbitrary_file_routes_rejected(self):
        self.start()
        for path in ('/../raw/fixture-v1.md', '/%2e%2e/raw/fixture-v1.md', '/%252e%252e/private',
                     '/raw/fixture-v1.md', '/wiki/log.md', '/.git/config', '/vendor/../app.js',
                     '/vendor/unknown.js', '/app.js%00', '/api/file?path=/etc/passwd'):
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertEqual(status, 404, body)
                self.assertNotIn(str(self.root).encode(), body)

    def test_foreign_hosts_origins_and_fetch_sites_rejected_before_graph_load(self):
        self.start()
        for headers in ({'Host': 'attacker.invalid'}, {'Host': '127.0.0.1:1'},
                        {'Origin': 'https://attacker.invalid'}, {'Origin': 'null'},
                        {'Sec-Fetch-Site': 'cross-site'}, {'Sec-Fetch-Site': 'same-site'}):
            with self.subTest(headers=headers), mock.patch.object(viewer, 'build_graph') as build:
                status, _, data = self.request('/api/graph', headers=headers)
                self.assertEqual(status, 403, data)
                build.assert_not_called()
        authority = 'http://127.0.0.1:' + str(self.server.server_port)
        self.assertEqual(self.request('/api/graph', headers={'Origin': authority, 'Sec-Fetch-Site': 'same-origin'})[0], 200)

    def test_duplicate_host_header_is_rejected(self):
        self.start()
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.putrequest('GET', '/api/graph')
        conn.putheader('Host', 'attacker.invalid')
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        conn.close()

    def test_forbidden_methods_are_read_only(self):
        self.start()
        before = self.files()
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE', 'CONNECT'):
            status, _, body = self.request('/api/graph', method=method, body=b'overwrite files')
            self.assertEqual(status, 405, body)
        self.assertEqual(self.files(), before)

    def test_refresh_is_fresh_and_errors_never_leak_partial_private_data(self):
        self.start()
        first = json.loads(self.request('/api/graph')[2])
        path = self.root / 'wiki/concepts/queue.md'
        path.write_text(path.read_text() + '\nNew explanatory sentence\n')
        second = json.loads(self.request('/api/graph')[2])
        self.assertNotEqual(first['source_digest'], second['source_digest'])
        self.mutate(lambda m: m.update(scope='project', title='PRIVATE_SENTINEL'))
        status, _, body = self.request('/api/graph')
        self.assertEqual(status, 422)
        self.assertNotIn(b'PRIVATE_SENTINEL', body)
        self.assertNotIn(str(self.root).encode(), body)
        self.assertNotIn('nodes', json.loads(body))

    def test_concurrent_edit_response_is_retryable_and_no_partial_graph(self):
        self.start()
        with mock.patch.object(viewer, 'build_graph', side_effect=viewer.invalid('concurrent_change', 'Knowledge changed while loading; refresh again.')):
            status, _, body = self.request('/api/graph')
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)['error']['code'], 'concurrent_change')

    def test_diagnostic_snapshot_returns_200_then_private_change_clears_all_data(self):
        self.start()
        (self.root / 'raw/fixture-v1.md').unlink()
        self.mutate(lambda m: None, '\n[Missing page](missing.md)\n')
        before = self.files()
        status, _, body = self.request('/api/graph')
        self.assertEqual(status, 200, body)
        graph = json.loads(body)
        self.assertEqual(graph['diagnostic_summary']['by_severity']['error'], 4)
        self.assertFalse(next(n for n in graph['nodes'] if n['kind'] == 'concept')['evidence_complete'])
        self.assertEqual(before, self.files())
        fixtures.write(self.root / 'raw/private.md', {'origin': 'PRIVATE_HTTP_CANARY', 'collected_at': '2026-01-01',
                       'scope': 'project', 'version': 'Private/1', 'permission': 'approved'}, 'PRIVATE_HTTP_CANARY')
        status, _, body = self.request('/api/graph')
        self.assertEqual(status, 422)
        self.assertNotIn(b'PRIVATE_HTTP_CANARY', body)
        self.assertEqual(set(json.loads(body)), {'error'})

    def test_drifted_index_is_withheld_and_private_index_frontmatter_returns_422(self):
        self.start()
        path = self.root / 'wiki/index.md'
        path.write_text('PRIVATE_INDEX_CANARY\n[unsafe](../docs/private.md)\n')
        status, _, body = self.request('/api/graph')
        self.assertEqual(status, 200, body)
        self.assertNotIn(b'PRIVATE_INDEX_CANARY', body)
        graph = json.loads(body)
        self.assertTrue(next(n for n in graph['nodes'] if n['kind'] == 'navigation')['body_withheld'])
        path.write_text('---json\n{"scope":"project"}\n---\nPRIVATE_INDEX_CANARY')
        status, _, body = self.request('/api/graph')
        self.assertEqual(status, 422)
        self.assertNotIn(b'PRIVATE_INDEX_CANARY', body)
        self.assertEqual(set(json.loads(body)), {'error'})

    def test_static_symlink_fails_closed(self):
        self.start()
        target = self.sandbox / 'secret.js'
        target.write_text('SECRET_ASSET')
        # Only this test's new temporary asset can be replaced; never repo/viewer.
        asset = self.temp_assets / 'app.js'
        asset.unlink()
        asset.symlink_to(target)
        status, _, body = self.request('/app.js')
        self.assertEqual(status, 503)
        self.assertNotIn(b'SECRET_ASSET', body)


if __name__ == '__main__':
    unittest.main()
