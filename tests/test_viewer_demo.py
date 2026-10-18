import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import export_vault
import viewer_demo
import wiki


class ViewerDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve()
        self.output = self.parent / 'demo'
        self.today = dt.datetime.now(dt.timezone.utc).date().isoformat()

    def snapshot(self, root):
        return {p.relative_to(root).as_posix(): p.read_bytes()
                for p in root.rglob('*') if p.is_file()}

    def test_default_is_valid_standalone_synthetic_demo(self):
        result = viewer_demo.generate(self.output)
        self.assertEqual(result['topics'], 8)
        self.assertEqual(result['date'], self.today)
        self.assertEqual(result['authored_notes'], 48)
        self.assertEqual(result['expected_viewer_nodes'], 49)
        self.assertEqual(len(self.snapshot(self.output)), 50)
        self.assertFalse((self.output / '.git').exists())
        self.assertEqual((self.output / 'wiki/log.md').read_text(), '# Wiki log\n')
        validation = wiki.lint(self.output)
        self.assertEqual(validation['errors'], [])
        self.assertFalse(validation['history_checked'])
        self.assertEqual(sum('OPEN CONTRADICTION' in w for w in validation['warnings']), 8)
        for folder in ('raw', 'wiki'):
            for path in wiki.inventory(self.output, folder):
                if path.name in ('index.md', 'log.md'):
                    continue
                metadata, body = wiki.read_page(path)
                self.assertTrue(metadata['fixture'])
                self.assertIn('SYNTHETIC DEMO', metadata['title'])
                self.assertIn('SYNTHETIC DEMO', body)
                self.assertIn('synthetic-demo', metadata['tags'])
                self.assertTrue(any(t.startswith('topic-') for t in metadata['tags']))
                self.assertNotIn(metadata.get('status'), ('reviewed', 'verified'))
                if folder == 'raw':
                    self.assertEqual(metadata['permission'], 'synthetic-fixture')
                    self.assertTrue(metadata['origin'].startswith('synthetic:'))

    def test_exact_versions_lineage_and_inference_remain_distinct(self):
        viewer_demo.generate(self.output, 1)
        current, _ = wiki.read_page(self.output / 'wiki/concepts/topic-001/current.md')
        prior, _ = wiki.read_page(self.output / 'wiki/concepts/topic-001/prior.md')
        comparison, _ = wiki.read_page(self.output / 'wiki/concepts/topic-001/comparison.md')
        lesson, _ = wiki.read_page(self.output / 'wiki/lessons/topic-001.md')
        self.assertEqual(prior['status'], 'superseded')
        self.assertEqual(prior['superseded_by'], 'wiki/concepts/topic-001/current.md')
        self.assertEqual(current['supersedes'], ['wiki/concepts/topic-001/prior.md'])
        self.assertEqual(comparison['contradictions'][0]['status'], 'open')
        self.assertEqual(len(set(comparison['contradictions'][0]['sources'])), 2)
        self.assertEqual(lesson['claims'][0]['kind'], 'inference')
        for version in ('1', '2'):
            matches = wiki.query(self.output, 'capacity', 'SyntheticTopic001/' + version)
            self.assertTrue(matches)
            for match in matches:
                for claim in match['claims']:
                    if claim['kind'] == 'evidence':
                        self.assertEqual(claim['sources'], [f'raw/topic-001/source-v{version}.md'])
            self.assertFalse(any(m['status'] == 'superseded' for m in matches))
        self.assertEqual(wiki.query(self.output, 'capacity', 'SyntheticTopic001/3'), [])

    def test_fixed_date_produces_identical_bytes_in_different_destinations(self):
        second = self.parent / 'second'
        first_result = viewer_demo.generate(self.output, 3, as_of='2026-01-01')
        second_result = viewer_demo.generate(second, 3, as_of='2026-01-01')
        self.assertEqual(first_result, second_result)
        self.assertEqual(self.snapshot(self.output), self.snapshot(second))
        for data in self.snapshot(self.output).values():
            self.assertNotIn(str(self.parent).encode(), data)

    def test_existing_file_and_directory_are_not_modified(self):
        for kind in ('file', 'directory'):
            with self.subTest(kind=kind):
                path = self.parent / kind
                if kind == 'file':
                    path.write_bytes(b'keep existing file')
                else:
                    path.mkdir()
                    (path / 'private.txt').write_bytes(b'keep existing directory')
                before = path.read_bytes() if path.is_file() else self.snapshot(path)
                with self.assertRaisesRegex(ValueError, 'new directory'):
                    viewer_demo.generate(path, 1)
                after = path.read_bytes() if path.is_file() else self.snapshot(path)
                self.assertEqual(before, after)

    def test_dangling_live_and_ancestor_symlinks_are_refused(self):
        target = self.parent / 'target'
        target.mkdir()
        (target / 'keep.txt').write_text('preserve', encoding='utf-8')
        link = self.parent / 'link'
        link.symlink_to(target, target_is_directory=True)
        dangling = self.parent / 'dangling'
        dangling.symlink_to(self.parent / 'absent')
        for destination in (link, dangling, link / 'new', link / '..' / 'sibling'):
            with self.subTest(destination=str(destination)):
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    viewer_demo.generate(destination, 1)
        self.assertEqual(self.snapshot(target), {'keep.txt': b'preserve'})
        self.assertFalse((self.parent / 'absent').exists())
        self.assertFalse((self.parent / 'sibling').exists())

    def test_invalid_topic_parameters_fail_before_creating_output(self):
        for topics in (0, -1, 201, 1.5, '8', True, None):
            with self.subTest(topics=topics):
                with self.assertRaisesRegex(ValueError, 'integer from 1 to 200'):
                    viewer_demo.generate(self.output, topics)
                self.assertFalse(self.output.exists())

    def test_maximum_topic_count_is_valid_without_unbounded_crosslinks(self):
        result = viewer_demo.generate(self.output, 200)
        self.assertEqual(result['authored_notes'], 1200)
        self.assertEqual(result['expected_viewer_nodes'], 1201)
        self.assertEqual(result['explicit_cross_topic_links'], 3)
        self.assertEqual(len(wiki.pages(self.output)), 800)
        self.assertEqual(len(wiki.inventory(self.output, 'raw')), 400)
        self.assertEqual(wiki.lint(self.output)['errors'], [])

    def test_invalid_dates_fail_before_creating_output(self):
        future = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1)).isoformat()
        for day in ('not-a-date', '2026-02-30', future, 42):
            with self.subTest(day=day):
                with self.assertRaises(ValueError):
                    viewer_demo.generate(self.output, 1, as_of=day)
                self.assertFalse(self.output.exists())

    def test_generated_graph_has_only_explicit_edges_and_expected_counts(self):
        viewer_demo.generate(self.output, 3)
        graph = json.loads(export_vault.build(self.output)['graph.json'])
        self.assertEqual(len(graph['nodes']), 6 * 3 + 3)  # Exporter adds Home/index/log.
        self.assertEqual(len(graph['edges']), 34 * 3 + 2 + 2)
        self.assertEqual({e['kind'] for e in graph['edges']},
                         {'link', 'sources', 'claim', 'contradiction',
                          'superseded_by', 'supersedes', 'navigation'})
        all_ids = {n['id'] for n in graph['nodes']}
        for edge in graph['edges']:
            self.assertIn(edge['from'], all_ids)
            self.assertIn(edge['to'], all_ids)

    def test_cli_help_success_and_invalid_bounds(self):
        command = [sys.executable, str(Path(viewer_demo.__file__).resolve())]
        help_result = subprocess.run([*command, '--help'], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn('--topics', help_result.stdout)
        self.assertIn('SYNTHETIC DEMO', help_result.stdout)
        result = subprocess.run([*command, '--output', str(self.output), '--topics', '1',
                                 '--date', '2026-01-01'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['synthetic_demo'])
        self.assertEqual(wiki.lint(self.output)['errors'], [])
        failed = subprocess.run([*command, '--output', str(self.parent / 'invalid'), '--topics', '201'],
                                capture_output=True, text=True)
        self.assertEqual(failed.returncode, 2)
        self.assertNotIn('Traceback', failed.stderr)
        self.assertFalse((self.parent / 'invalid').exists())


if __name__ == '__main__':
    unittest.main()
