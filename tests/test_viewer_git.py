"""Real local Git history, confinement, limits and compare HTTP regressions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import test_viewer as support
import demo
import fixtures
import viewer
import viewer_git
import wiki


class HistoryTests(unittest.TestCase):
    setUp = support.ViewerTests.setUp
    files = support.ViewerTests.files
    mutate = support.ViewerTests.mutate

    def second(self):
        fixtures.seed(self.root, 2)
        return demo.commit(self.root, 'Synthetic second revision')

    def compare(self, base=None, target=None):
        return viewer_git.compare(self.root, base or self.base, target or viewer.revision(self.root))

    def object(self, kind, content):
        result = subprocess.run(['git', '-C', str(self.root), 'hash-object', '-w', '-t', kind, '--literally', '--stdin'],
                                input=content, capture_output=True, check=True)
        return result.stdout.decode('ascii').strip()

    def commit_raw_tree(self, tree):
        wiki_tree = wiki.git(self.root, 'rev-parse', self.base + ':wiki')
        root = self.object('tree', b'40000 raw\0' + bytes.fromhex(tree) + b'40000 wiki\0' + bytes.fromhex(wiki_tree))
        commit = wiki.git(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                          'commit-tree', root, '-p', self.base, '-m', 'Adversarial tree fixture')
        wiki.git(self.root, 'update-ref', 'HEAD', commit)
        return commit

    def test_loose_history_returns_structural_summaries_and_explicit_edge_provenance(self):
        target = self.second()
        before = self.files()
        result = self.compare()
        self.assertEqual(result['base_revision'], self.base)
        self.assertEqual(result['target_revision'], target)
        self.assertEqual(result['head_revision'], target)
        self.assertEqual(result['corpus_id'], viewer.build_graph(self.root)['corpus_id'])
        self.assertEqual([node['id'] for node in result['nodes']['added']], ['raw/fixture-v2.md'])
        changed = {node['id']: node for node in result['nodes']['changed']}
        self.assertIn('body', changed['wiki/concepts/queue.md']['fields'])
        self.assertNotIn('body', changed['wiki/concepts/queue.md']['after'])
        self.assertNotIn('metadata', changed['wiki/concepts/queue.md']['before'])
        self.assertTrue(all(edge['explicit'] and edge['provenance']['file'] == edge['source'] for edge in result['edges']['added']))
        self.assertEqual(before, self.files())
        self.assertEqual(result, self.compare())
        self.assertEqual(self.compare(target, target)['stats']['nodes'], {'added': 0, 'removed': 0, 'changed': 0})
        reverse = self.compare(target, self.base)
        self.assertEqual([n['id'] for n in reverse['nodes']['removed']], ['raw/fixture-v2.md'])

    def test_packed_objects_and_packed_head_refs_produce_the_same_result(self):
        self.second()
        before = self.compare()
        wiki.git(self.root, 'gc', '--prune=now')
        wiki.git(self.root, 'pack-refs', '--all')
        self.assertTrue(list((self.root / '.git/objects/pack').glob('*.pack')))
        self.assertEqual(before, self.compare())

    def test_pack_count_headers_and_symlinked_pack_are_rejected(self):
        wiki.git(self.root, 'gc', '--prune=now')
        pack = next((self.root / '.git/objects/pack').glob('*.pack'))
        original = pack.read_bytes()
        pack.unlink()  # Replace only this disposable fixture's read-only pack.
        pack.write_bytes(original[:8] + (viewer_git.MAX_OBJECTS + 1).to_bytes(4, 'big') + original[12:])
        with self.assertRaises(viewer.ViewerError):
            self.compare()
        pack.unlink()
        outside = self.sandbox / 'PRIVATE_PACK_CANARY'
        outside.write_bytes(original)
        pack.symlink_to(outside)
        with self.assertRaises(viewer.ViewerError) as error:
            self.compare()
        self.assertNotIn('PRIVATE_PACK_CANARY', str(error.exception))

    def test_relation_status_changes_pair_without_fabricated_links(self):
        base = self.second()
        self.mutate(lambda m: m['contradictions'][0].update(status='resolved', resolution='Fixture-only resolution.'))
        target = demo.commit(self.root, 'Resolve explicit fixture contradiction')
        result = self.compare(base, target)
        changed = result['edges']['changed']
        self.assertEqual(len(changed), 2)
        self.assertFalse(result['edges']['added'])
        self.assertFalse(result['edges']['removed'])
        for record in changed:
            self.assertTrue(record['id'].startswith('relation-'))
            self.assertEqual(record['before']['status'], 'open')
            self.assertEqual(record['after']['status'], 'resolved')
            self.assertEqual(record['before']['provenance'], record['after']['provenance'])

    def test_full_sha_only_and_commits_must_be_current_head_ancestors(self):
        self.second()
        for value in ('HEAD', self.base[:8], self.base + '^', '--help', 'a' * 40, 'A' * 40, '../.git/config'):
            with self.subTest(value=value), self.assertRaises(viewer.ViewerError):
                self.compare(value)
        other = wiki.git(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                         'commit-tree', self.base + '^{tree}', '-p', self.base, '-m', 'Unreachable sibling')
        self.assertNotEqual(other, self.base)
        with self.assertRaises(viewer.ViewerError) as error:
            self.compare(other)
        self.assertEqual(error.exception.code, 'invalid_revision')

    def test_misplaced_parent_header_cannot_add_non_git_ancestor(self):
        tree = wiki.git(self.root, 'rev-parse', self.base + '^{tree}')
        side = wiki.git(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                        'commit-tree', tree, '-p', self.base, '-m', 'Unreachable side')
        data = (f'tree {tree}\nparent {self.base}\nauthor Fixture <fixture@example.invalid> 1000000000 +0000\n'
                f'committer Fixture <fixture@example.invalid> 1000000000 +0000\nparent {side}\n\nMalformed fixture\n').encode('ascii')
        malformed = self.object('commit', data)
        wiki.git(self.root, 'update-ref', 'HEAD', malformed)
        self.assertNotIn(side, wiki.git(self.root, 'rev-list', 'HEAD').splitlines())
        with self.assertRaises(viewer.ViewerError):
            self.compare(side, malformed)

    def test_private_old_snapshot_denies_entire_comparison_even_after_removal(self):
        fixtures.write(self.root / 'raw/private.md', {'origin': 'OLD_PRIVATE_CANARY', 'collected_at': '2026-01-01',
                       'scope': 'project', 'version': 'Private/1', 'permission': 'approved'}, 'OLD_PRIVATE_CANARY')
        private = demo.commit(self.root, 'Private fixture must never display')
        (self.root / 'raw/private.md').unlink()
        shared = demo.commit(self.root, 'Remove private fixture')
        for base, target in ((private, shared), (shared, private)):
            with self.subTest(base=base), self.assertRaises(viewer.ViewerError) as error:
                self.compare(base, target)
            self.assertEqual(error.exception.code, 'private_scope')
            self.assertNotIn('OLD_PRIVATE_CANARY', str(error.exception))

    def test_git_config_includes_replacements_and_inherited_git_environment_are_inert(self):
        target = self.second()
        expected = self.compare()
        config = self.root / '.git/config'
        outside = self.sandbox / 'PRIVATE_CONFIG_CANARY'
        outside.write_text('this is deliberately not valid git config\n')
        config.write_text('[include]\npath = ' + str(outside) + '\n[core]\nfsmonitor = NEVER_EXECUTE\n')
        replacement = self.root / '.git/refs/replace' / target
        replacement.parent.mkdir()
        replacement.write_text(self.base + '\n')
        trace = self.sandbox / 'SHOULD_NOT_WRITE_TRACE'
        env = {'GIT_DIR': str(self.sandbox), 'GIT_OBJECT_DIRECTORY': str(self.sandbox), 'GIT_WORK_TREE': str(self.sandbox),
               'GIT_ALTERNATE_OBJECT_DIRECTORIES': str(self.sandbox), 'GIT_CONFIG_GLOBAL': str(outside),
               'GIT_CONFIG_SYSTEM': str(outside), 'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'include.path',
               'GIT_CONFIG_VALUE_0': str(outside), 'GIT_TRACE': str(trace), 'GIT_SSH_COMMAND': 'NEVER_EXECUTE'}
        opened = []
        original = viewer.regular_bytes
        def capture(fd, name, limit):
            opened.append(name)
            return original(fd, name, limit)
        with mock.patch.dict(os.environ, env), mock.patch.object(viewer, 'regular_bytes', side_effect=capture):
            self.assertEqual(expected, self.compare())
        self.assertNotIn('config', opened)
        self.assertNotIn('PRIVATE_CONFIG_CANARY', opened)
        self.assertFalse(trace.exists())

    def test_alternates_and_symlinked_objects_fail_without_following_them(self):
        info = self.root / '.git/objects/info'
        for name in ('alternates', 'http-alternates'):
            path = info / name
            path.write_text(str(self.sandbox / 'PRIVATE_OBJECTS_CANARY'))
            with self.subTest(name=name), self.assertRaises(viewer.ViewerError) as error:
                self.compare()
            self.assertNotIn('PRIVATE_OBJECTS_CANARY', str(error.exception))
            path.unlink()
        loose = next(path for path in (self.root / '.git/objects').glob('*/*') if path.is_file())
        data = loose.read_bytes()
        outside = self.sandbox / 'PRIVATE_LOOSE_CANARY'
        outside.write_bytes(data)
        loose.unlink()
        loose.symlink_to(outside)
        with self.assertRaises(viewer.ViewerError):
            self.compare()

    def test_external_gitfiles_and_symlinked_git_metadata_are_unsupported(self):
        original = self.root / '.git'
        outside = self.sandbox / 'outside-git'
        original.rename(outside)
        original.write_text('gitdir: ' + str(outside) + '\n')
        with self.assertRaises(viewer.ViewerError):
            self.compare(self.base, self.base)
        original.unlink()
        original.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(viewer.ViewerError):
            self.compare(self.base, self.base)

    def test_historical_symlink_gitlink_and_nonmarkdown_are_rejected(self):
        link = self.root / 'raw/linked.md'
        link.symlink_to(self.sandbox / 'PRIVATE_LINK_CANARY')
        bad = demo.commit(self.root, 'Unsafe raw symlink')
        with self.assertRaises(viewer.ViewerError):
            self.compare(self.base, bad)
        link.unlink()
        demo.commit(self.root, 'Remove unsafe symlink')
        path = self.root / 'wiki/private.bin'
        path.write_bytes(b'PRIVATE_BINARY_CANARY')
        bad = demo.commit(self.root, 'Non-Markdown file')
        with self.assertRaises(viewer.ViewerError):
            self.compare(self.base, bad)
        path.unlink()
        demo.commit(self.root, 'Remove non-Markdown file')
        wiki.git(self.root, 'update-index', '--add', '--cacheinfo', '160000,' + self.base + ',raw/submodule')
        wiki.git(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Unsafe gitlink')
        with self.assertRaises(viewer.ViewerError):
            self.compare()

    def test_tree_path_traversal_and_dotgit_components_are_never_materialized(self):
        blob = wiki.git(self.root, 'rev-parse', self.base + ':raw/fixture-v1.md')
        for name in (b'../PRIVATE_PATH_CANARY.md', b'.git/PRIVATE_PATH_CANARY.md', b'PRIVATE\\PATH.md'):
            raw = self.object('tree', b'100644 ' + name + b'\0' + bytes.fromhex(blob))
            target = self.commit_raw_tree(raw)
            with self.subTest(name=name), self.assertRaises(viewer.ViewerError) as error:
                self.compare(self.base, target)
            self.assertNotIn('PRIVATE_PATH_CANARY', str(error.exception))
        self.assertFalse((self.sandbox / 'PRIVATE_PATH_CANARY.md').exists())

    def test_compressed_oversized_tree_is_rejected_before_content_read(self):
        raw = self.object('tree', b'A' * (viewer_git.MAX_TREE_BYTES + 1))
        target = self.commit_raw_tree(raw)
        data_requests = []
        real = viewer_git.Store.run
        def capture(store, arguments, limit, input_data=b''):
            if arguments == ['cat-file', '--batch']:
                data_requests.extend(input_data.decode('ascii').splitlines())
            return real(store, arguments, limit, input_data)
        with mock.patch.object(viewer_git.Store, 'run', capture), self.assertRaises(viewer.ViewerError) as error:
            self.compare(self.base, target)
        self.assertEqual(error.exception.code, 'history_limit')
        self.assertNotIn(raw, data_requests)

    def test_missing_object_fails_locally_without_fetch_or_other_git_commands(self):
        blob = wiki.git(self.root, 'rev-parse', self.base + ':raw/fixture-v1.md')
        (self.root / '.git/objects' / blob[:2] / blob[2:]).unlink()
        commands = []
        real = viewer_git.Store.run
        def capture(store, arguments, limit, input_data=b''):
            commands.append(arguments)
            return real(store, arguments, limit, input_data)
        with mock.patch.object(viewer_git.Store, 'run', capture), self.assertRaises(viewer.ViewerError):
            self.compare()
        self.assertTrue(commands)
        self.assertTrue(all(command[0] == 'cat-file' for command in commands))

    def test_git_directory_replacement_during_copy_is_detected(self):
        replacement = self.sandbox / 'replacement-repo'
        shutil.copytree(self.root, replacement)
        (replacement / 'unrelated.txt').write_text('Another repository head')
        demo.commit(replacement, 'Different HEAD')
        real = viewer_git.Store.copy_objects
        def replace(store, git_fd, head):
            real(store, git_fd, head)
            (self.root / '.git').rename(self.sandbox / 'old-git')
            shutil.copytree(replacement / '.git', self.root / '.git')
        with mock.patch.object(viewer_git.Store, 'copy_objects', replace), self.assertRaises(viewer.ViewerError) as error:
            self.compare(self.base, self.base)
        self.assertEqual(error.exception.code, 'concurrent_change')

    def test_log_and_outside_corpus_blobs_never_enter_cat_file_requests(self):
        log = self.root / 'wiki/log.md'
        log.write_text('PRIVATE_LOG_CANARY\n')
        docs = self.root / 'docs'
        docs.mkdir()
        (docs / 'private.md').write_text('PRIVATE_DOC_CANARY\n')
        target = demo.commit(self.root, 'Excluded content')
        forbidden = {wiki.git(self.root, 'rev-parse', target + ':wiki/log.md'), wiki.git(self.root, 'rev-parse', target + ':docs/private.md')}
        real = viewer_git.Store.run
        requested = []
        def capture(store, arguments, limit, input_data=b''):
            if arguments[0] == 'cat-file':
                requested.extend(input_data.decode('ascii').splitlines())
            return real(store, arguments, limit, input_data)
        with mock.patch.object(viewer_git.Store, 'run', capture):
            result = self.compare()
        self.assertFalse(forbidden.intersection(requested))
        self.assertNotIn('PRIVATE_', json.dumps(result))

    def test_object_commit_tree_blob_and_response_limits_fail_closed(self):
        self.second()
        for name, value in (('MAX_STORE_BYTES', 1), ('MAX_OBJECT_FILE_BYTES', 1), ('MAX_OBJECTS', 1),
                            ('MAX_COMMITS', 1), ('MAX_COMMIT_BYTES', 32), ('MAX_HISTORY_COMMIT_BYTES', 32),
                            ('MAX_TREE_BYTES', 16), ('MAX_RESPONSE_BYTES', 1)):
            with self.subTest(limit=name), mock.patch.object(viewer_git, name, value), self.assertRaises(viewer.ViewerError):
                self.compare()
        for name, value in (('MAX_FILE_BYTES', 32), ('MAX_TOTAL_BYTES', 100), ('MAX_NOTES', 1), ('MAX_DIRECTORY_ENTRIES', 1)):
            with self.subTest(limit=name), mock.patch.object(viewer, name, value), self.assertRaises(viewer.ViewerError):
                self.compare()

    def test_subprocess_stdout_and_time_are_bounded_and_child_is_reaped(self):
        original = subprocess.Popen
        for source, limit, seconds in (("import sys; sys.stdout.write('X'*100000)", 10, 2),
                                       ('import time; time.sleep(10)', 100, .1)):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                store = viewer_git.Store(viewer, directory)
                store.deadline = time.monotonic() + seconds
                children = []
                def spawn(*args, **kwargs):
                    child = original([sys.executable, '-c', source], **kwargs)
                    children.append(child)
                    return child
                with mock.patch.object(viewer_git.subprocess, 'Popen', side_effect=spawn):
                    with self.assertRaises(viewer.ViewerError) as error:
                        store.run(['ignored'], limit)
                self.assertEqual(error.exception.code, 'history_limit')
                self.assertIsNotNone(children[0].poll())

    def test_corpus_id_stable_for_updates_unique_for_roots_and_root_replacement_rejected(self):
        first = viewer.build_graph(self.root)['corpus_id']
        self.mutate(lambda m: None, '\nUpdated local content.\n')
        self.assertEqual(viewer.build_graph(self.root)['corpus_id'], first)
        copied = self.sandbox / 'copied'
        shutil.copytree(self.root, copied)
        self.assertNotEqual(viewer.build_graph(copied)['corpus_id'], first)
        self.assertNotIn(str(self.root), first)
        original, calls = viewer.scan, 0
        def replace(fd):
            nonlocal calls
            calls += 1
            result = original(fd)
            if calls == 2:
                self.root.rename(self.sandbox / 'old-root')
                shutil.copytree(copied, self.root)
            return result
        with mock.patch.object(viewer, 'scan', side_effect=replace), self.assertRaises(viewer.ViewerError) as error:
            viewer.build_graph(self.root)
        self.assertEqual(error.exception.code, 'concurrent_change')


class HistoryHTTPTests(unittest.TestCase):
    setUp = support.ViewerTests.setUp
    start = support.ViewerHTTPTests.start
    request = support.ViewerHTTPTests.request
    files = support.ViewerTests.files

    def test_compare_http_strict_query_same_origin_and_read_only(self):
        fixtures.seed(self.root, 2)
        target = demo.commit(self.root, 'Second fixture')
        self.start()
        path = '/api/compare?base=' + self.base + '&target=' + target
        before = self.files()
        status, _, body = self.request(path)
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)['target_revision'], target)
        self.assertNotIn('body', json.loads(body)['nodes']['added'][0])
        self.assertEqual(self.request(path, headers={'Origin': 'https://attacker.invalid'})[0], 403)
        self.assertEqual(self.request(path, method='POST')[0], 405)
        for query in ('', '?base=HEAD&target=' + target, '?base=' + self.base,
                      '?base=' + self.base + '&target=' + target + '&extra=x',
                      '?base=' + self.base + '&base=' + target, '?base=%ff&target=' + target):
            with self.subTest(query=query):
                status, _, body = self.request('/api/compare' + query)
                self.assertEqual(status, 422, body)
                self.assertEqual(set(json.loads(body)), {'error'})
        self.assertEqual(before, self.files())

    def test_old_private_history_never_returns_partial_http_diff(self):
        fixtures.write(self.root / 'raw/private.md', {'origin': 'OLD_PRIVATE_CANARY', 'collected_at': '2026-01-01',
                       'scope': 'project', 'version': 'Private/1', 'permission': 'approved'}, 'OLD_PRIVATE_CANARY')
        private = demo.commit(self.root, 'Private fixture')
        (self.root / 'raw/private.md').unlink()
        shared = demo.commit(self.root, 'Shared fixture restored')
        self.start()
        status, _, body = self.request('/api/compare?base=' + private + '&target=' + shared)
        self.assertEqual(status, 422)
        self.assertEqual(set(json.loads(body)), {'error'})
        self.assertNotIn(b'OLD_PRIVATE_CANARY', body)
        self.assertNotIn(str(self.root).encode(), body)


if __name__ == '__main__':
    unittest.main()
