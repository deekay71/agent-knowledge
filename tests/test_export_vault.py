import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import demo
import export_vault as vault
import fixtures
import wiki


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()/'repo'
        self.root.mkdir()
        wiki.git(self.root, 'init', '-b', 'contrib/test')
        fixtures.seed(self.root)
        demo.commit(self.root, 'Baseline')
        self.output = self.root/'vault'

    def change(self, **values):
        path = self.root/'wiki/concepts/queue.md'
        meta, body = wiki.read_page(path)
        meta.update(values)
        fixtures.write(path, meta, body)
        (self.root/'wiki/index.md').write_text(wiki.index_text(self.root))

    def snapshot(self, path):
        return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*') if p.is_file() and '.git' not in p.relative_to(path).parts}

    def test_export_deterministic_read_only_sources_and_provenance(self):
        original = vault.input_files(self.root)
        first = vault.build(self.root)
        self.assertEqual(first, vault.build(self.root))
        vault.export(self.root, self.output)
        self.assertEqual(first, self.snapshot(self.output))
        self.assertEqual(original, vault.input_files(self.root))
        self.assertEqual(vault.check(self.root, self.output)['files'], 8)
        manifest = json.loads(first[vault.MANIFEST])
        for name, value in original.items():
            self.assertEqual(manifest['inputs'][name], hashlib.sha256(value).hexdigest())
        external = self.root.parent/'external'
        vault.export(self.root, external)
        self.assertEqual(self.snapshot(external), first)

    def test_generated_links_and_graph_nodes_resolve_inside_vault(self):
        files = vault.build(self.root)
        for name, value in files.items():
            if not name.endswith('.md'):
                continue
            for target in wiki.LINK.findall(value.decode()):
                parts = urlsplit(target)
                if parts.scheme or not parts.path:
                    continue
                dest = os.path.normpath(str(Path(name).parent / unquote(parts.path)))
                self.assertIn(dest, files, (name, target))
        graph = json.loads(files['graph.json'])
        ids = {node['id'] for node in graph['nodes']}
        for edge in graph['edges']:
            self.assertIn(edge['from'], ids)
            self.assertIn(edge['to'], ids)
        self.assertIn({'from': 'wiki/concepts/queue.md', 'to': 'raw/fixture-v1.md', 'kind': 'sources'}, graph['edges'])

    def test_v2_contradictions_and_claim_labels_survive(self):
        fixtures.seed(self.root, 2)
        files = vault.build(self.root)
        note = files['wiki/concepts/queue.md'].decode()
        self.assertIn('**OPEN**', note)
        self.assertIn('**inference**', note)
        self.assertIn('**evidence**', note)
        self.assertIn('FixtureQueue/1', note)
        self.assertIn('FixtureQueue/2', note)
        graph = json.loads(files['graph.json'])
        conflicts = [e for e in graph['edges'] if e['kind'] == 'contradiction']
        self.assertEqual({e['to'] for e in conflicts}, {'raw/fixture-v1.md', 'raw/fixture-v2.md'})
        self.assertTrue(all(e['status'] == 'open' for e in conflicts))

    def test_supersession_and_review_references_are_actual_links(self):
        review = self.root/'docs/review.md'
        review.parent.mkdir()
        review.write_text('# Fixture review\nReviewed, not verified.\n')
        self.change(status='superseded', superseded_by='wiki/lessons/versioning.md', review_record='docs/review.md')
        path = self.root/'wiki/lessons/versioning.md'
        m, b = wiki.read_page(path)
        m['supersedes'] = ['wiki/concepts/queue.md']
        fixtures.write(path, m, b)
        files = vault.build(self.root)
        self.assertIn('docs/review.md', files)
        note = files['wiki/concepts/queue.md'].decode()
        self.assertIn('(../../docs/review.md)', note)
        graph = json.loads(files['graph.json'])
        for kind in ('superseded_by', 'supersedes', 'review_record'):
            self.assertTrue(any(e['kind'] == kind for e in graph['edges']))

    def test_unknown_is_not_promoted_to_evidence(self):
        self.change(claims=[{'kind': 'unknown', 'text': 'No measured data', 'sources': [], 'applies_to': ['FixtureQueue/1']}])
        note = vault.build(self.root)['wiki/concepts/queue.md'].decode()
        self.assertIn('**unknown**', note)
        self.assertIn('Sources: none; unknown', note)

    def test_flat_yaml_quotes_metadata_and_escapes_rendered_text(self):
        title = 'Công suất: "8"\n---\n[bad](https://example.invalid)\u2028'
        self.change(title=title)
        note = vault.build(self.root)['wiki/concepts/queue.md'].decode()
        self.assertTrue(note.startswith('---\n'))
        encoded = next(row[len('title: '):] for row in note.splitlines() if row.startswith('title: '))
        self.assertEqual(json.loads(encoded), title)
        self.assertNotIn('---json', note)
        self.assertNotIn('claims:', note.split('\n---\n')[0])

    def test_markdown_filename_with_spaces_and_unicode(self):
        path = self.root/'wiki/lessons/versioning.md'
        new = self.root/'wiki/lessons/bài học.md'
        path.rename(new)
        concept = self.root/'wiki/concepts/queue.md'
        concept.write_text(concept.read_text().replace('../lessons/versioning.md', '../lessons/b%C3%A0i%20h%E1%BB%8Dc.md'))
        (self.root/'wiki/index.md').write_text(wiki.index_text(self.root))
        files = vault.build(self.root)
        self.assertIn('wiki/lessons/bài học.md', files)
        self.assertIn('b%C3%A0i%20h%E1%BB%8Dc.md', files['wiki/concepts/queue.md'].decode())

    def test_source_update_requires_refresh_and_old_raw_stays_unchanged(self):
        raw = (self.root/'raw/fixture-v1.md').read_bytes()
        vault.export(self.root, self.output)
        old = self.snapshot(self.output)
        fixtures.seed(self.root, 2)
        with self.assertRaisesRegex(ValueError, 'Vault drift'):
            vault.check(self.root, self.output)
        self.assertEqual(old, self.snapshot(self.output))
        vault.export(self.root, self.output, refresh=True)
        vault.check(self.root, self.output)
        self.assertEqual(raw, (self.root/'raw/fixture-v1.md').read_bytes())

    def test_export_never_overwrites_existing_destination(self):
        self.output.mkdir()
        (self.output/'personal.md').write_text('keep')
        for refresh in (False, True):
            with self.assertRaises(ValueError):
                vault.export(self.root, self.output, refresh=refresh)
        self.assertEqual((self.output/'personal.md').read_text(), 'keep')

    def test_refresh_refuses_edits_unknown_files_and_deleted_notes(self):
        vault.export(self.root, self.output)
        old = self.snapshot(self.output)
        for name, value in [('Home.md', b'my edits'), ('personal.md', b'my notes'), ('raw/fixture-v1.md', None)]:
            path = self.output/name
            if value is None:
                path.unlink()
            else:
                path.write_bytes(value)
            before = self.snapshot(self.output)
            with self.assertRaisesRegex(ValueError, 'Local edits'):
                vault.export(self.root, self.output, refresh=True)
            self.assertEqual(before, self.snapshot(self.output))
            if name in old:
                path.write_bytes(old[name])
            else:
                path.unlink()

    def test_obsidian_preferences_are_untouched(self):
        vault.export(self.root, self.output)
        settings = self.output/'.obsidian/workspace.json'
        settings.parent.mkdir()
        settings.write_text('{"personal": true}')
        vault.check(self.root, self.output)
        fixtures.seed(self.root, 2)
        vault.export(self.root, self.output, refresh=True)
        self.assertEqual(settings.read_text(), '{"personal": true}')

    def test_symlinks_and_source_paths_are_refused(self):
        vault.export(self.root, self.output)
        alias = self.root.parent/'alias'
        alias.symlink_to(self.output, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            vault.export(self.root, alias, refresh=True)
        (self.output/'.obsidian').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            vault.check(self.root, self.output)
        for target in (self.root, self.root/'raw', self.root/'wiki/view', self.root.parent):
            with self.assertRaises(ValueError):
                vault.export(self.root, target)

    def test_source_symlink_and_private_metadata_are_refused(self):
        path = self.root/'raw/fixture-v1.md'
        data = path.read_bytes()
        path.unlink()
        other = self.root.parent/'source.md'
        other.write_bytes(data)
        path.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            vault.build(self.root)
        path.unlink()
        path.write_bytes(data)
        self.change(scope='project')
        with self.assertRaisesRegex(ValueError, 'Project/session'):
            vault.build(self.root)

    def test_invalid_index_and_raw_links_fail_without_partial_output(self):
        path = self.root/'raw/fixture-v1.md'
        path.write_text(path.read_text() + '\n[missing](missing.md)\n')
        with self.assertRaisesRegex(ValueError, 'outside the exported'):
            vault.export(self.root, self.output)
        self.assertFalse(self.output.exists())
        (self.root/'wiki/index.md').write_text('invalid')
        with self.assertRaisesRegex(ValueError, 'Index drift'):
            vault.build(self.root)

    def test_reserved_review_filename_is_refused(self):
        (self.root/'Home.md').write_text('# Critical review evidence')
        self.change(review_record='Home.md')
        with self.assertRaisesRegex(ValueError, 'collides'):
            vault.build(self.root)

    def test_portable_names_reject_unsafe_cross_platform_characters(self):
        for value in ('wiki/a#b.md', 'wiki/NUL.md', 'wiki/a|b.md', 'wiki/../a.md', 'wiki/a%20b.md'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                vault.portable_name(value)

    def test_source_changes_during_export_detected(self):
        original = vault.input_files(self.root)
        changed = dict(original, extra=b'changed')
        with patch.object(vault, 'input_files', side_effect=[original, changed]):
            with self.assertRaisesRegex(ValueError, 'changed during'):
                vault.build(self.root)

    def test_refresh_io_failure_rolls_back_previous_files(self):
        vault.export(self.root, self.output)
        old = self.snapshot(self.output)
        fixtures.seed(self.root, 2)
        write = wiki.atomic_write
        calls = []
        def fail_once(path, data):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('simulated disk failure')
            write(path, data)
        with patch.object(wiki, 'atomic_write', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'simulated'):
                vault.export(self.root, self.output, refresh=True)
        self.assertEqual(old, self.snapshot(self.output))

    def test_concurrent_export_lock_preserves_output(self):
        vault.export(self.root, self.output)
        before = self.snapshot(self.output)
        with vault.output_lock(self.output):
            with self.assertRaisesRegex(ValueError, 'Another exporter'):
                vault.export(self.root, self.output, refresh=True)
        self.assertEqual(before, self.snapshot(self.output))

    def test_log_details_are_literal_not_graph_edges(self):
        wiki.record(self.root, 'query', '[not a real link](private.md) ` ```')
        files = vault.build(self.root)
        self.assertIn('````text', files['wiki/log.md'].decode())
        self.assertFalse(any(e['from'] == 'wiki/log.md' for e in json.loads(files['graph.json'])['edges']))

    def test_code_examples_are_literal_and_not_graph_edges(self):
        path = self.root/'raw/fixture-v1.md'
        example = ('\n```markdown\n[Example](example.md)\n```\n'
                   '\n~~~md\n[Example](../wiki/lessons/./versioning.md)\n~~~\n'
                   '\nUse `[inline](unknown.md)` and ``[other](missing.md) `code` ``.\n'
                   '\n    [Indented](missing.md)\n')
        path.write_text(path.read_text() + example)
        files = vault.build(self.root)
        self.assertIn(example.rstrip(), files['raw/fixture-v1.md'].decode())
        graph = json.loads(files['graph.json'])
        self.assertFalse(any(e['from'] == 'raw/fixture-v1.md' for e in graph['edges']))

    def test_metadata_entity_is_preserved_as_literal_text(self):
        self.change(claims=[{'kind': 'inference', 'text': 'Literal &lt;8&gt; differs from <8>.', 'sources': [], 'applies_to': ['FixtureQueue/1']}])
        note = vault.build(self.root)['wiki/concepts/queue.md'].decode()
        self.assertIn('Literal &amp;lt;8&amp;gt; differs from \\<8\\>.', note)

    def test_unclosed_fence_cannot_hide_generated_claims(self):
        path = self.root/'wiki/concepts/queue.md'
        path.write_text(path.read_text() + '\n```text\nUnclosed example\n')
        self.assertEqual(wiki.lint(self.root)['errors'], [])
        with self.assertRaisesRegex(ValueError, 'Unclosed fenced'):
            vault.export(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_file_directory_transition_refused_before_any_write(self):
        vault.export(self.root, self.output)
        old = self.snapshot(self.output)
        lesson = self.root/'wiki/lessons/versioning.md'
        data = lesson.read_bytes()
        lesson.unlink()
        lesson.mkdir()
        # Rewrite the backlink for the additional directory level.
        (lesson/'detail.md').write_text(data.decode().replace('../concepts/queue.md', '../../concepts/queue.md'))
        concept = self.root/'wiki/concepts/queue.md'
        concept.write_text(concept.read_text().replace('../lessons/versioning.md', '../lessons/versioning.md/detail.md'))
        (self.root/'wiki/index.md').write_text(wiki.index_text(self.root))
        self.assertEqual(wiki.lint(self.root)['errors'], [])
        with self.assertRaisesRegex(ValueError, 'shape changed'):
            vault.export(self.root, self.output, refresh=True)
        self.assertEqual(old, self.snapshot(self.output))


if __name__ == '__main__':
    unittest.main()
