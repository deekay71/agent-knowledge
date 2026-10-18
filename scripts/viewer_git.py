"""Bounded local history comparisons. Original Git configuration is never loaded."""
import hashlib
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import struct
import subprocess
import tempfile
import time

MAX_STORE_BYTES = 256 * 1024 * 1024
MAX_OBJECT_FILE_BYTES = 128 * 1024 * 1024
MAX_OBJECTS = 10000
MAX_COMMITS = 2000
MAX_COMMIT_BYTES = 1024 * 1024
MAX_HISTORY_COMMIT_BYTES = 16 * 1024 * 1024
MAX_TREE_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
MAX_SECONDS = 20
SHA = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
NODE_FIELDS = ('id', 'title', 'kind', 'summary', 'status', 'fixture', 'scope', 'tags', 'applies_to', 'evidence_complete')


class Store:
    def __init__(self, api, directory):
        self.api, self.directory = api, Path(directory)
        self.deadline = time.monotonic() + MAX_SECONDS
        self.bytes = self.objects = self.entries = 0
        self.git = shutil.which('git', path=os.defpath)
        if not self.git:
            raise api.invalid('history_unavailable', 'Local Git history comparison is unavailable.')

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise self.api.invalid('history_limit', 'History comparison exceeded its time limit.')
        return remaining

    def fail(self):
        raise self.api.invalid('invalid_history', 'History is unavailable or unsupported; no comparison was returned.')

    def head(self, git_fd):
        value = self.api.regular_bytes(git_fd, 'HEAD', 4096)[0].decode('ascii').strip()
        if SHA.fullmatch(value):
            return value
        if not value.startswith('ref: refs/'):
            self.fail()
        ref = value[5:]
        self.api.canonical_reference(ref, 'refs')
        try:
            value = self.api.relative_bytes(git_fd, ref, 4096).decode('ascii').strip()
        except FileNotFoundError:
            packed = self.api.regular_bytes(git_fd, 'packed-refs', self.api.MAX_FILE_BYTES)[0].decode('ascii')
            matches = [line.split(' ', 1)[0] for line in packed.splitlines() if line.endswith(' ' + ref)]
            if len(matches) != 1:
                self.fail()
            value = matches[0]
        if not SHA.fullmatch(value):
            self.fail()
        return value

    def copy_objects(self, git_fd, head):
        """Only regular loose objects and pack/idx pairs enter the temporary store."""
        width = len(head)
        pack_counts, index_counts = {}, {}
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        def walk(fd, destination, level):
            before = self.api.signature(os.fstat(fd))
            for name in sorted(os.listdir(fd)):
                self.remaining()
                self.entries += 1
                if self.entries > MAX_OBJECTS * 3:
                    raise self.api.invalid('history_limit', 'History object count exceeds comparison limits.')
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    self.fail()
                if level == 'objects' and (re.fullmatch(r'[0-9a-f]{2}', name) or name in ('pack', 'info')):
                    child = os.open(name, flags, dir_fd=fd)
                    try:
                        if self.api.signature(os.fstat(child)) != self.api.signature(info):
                            self.fail()
                        target = destination / name
                        target.mkdir()
                        walk(child, target, name)
                    finally:
                        os.close(child)
                    continue
                if not stat.S_ISREG(info.st_mode):
                    self.fail()
                if level == 'info':
                    if name in ('alternates', 'http-alternates'):
                        self.fail()
                    continue  # Never copy commit graphs or other acceleration/config data.
                if level == 'pack':
                    match = re.fullmatch(r'pack-([0-9a-f]{' + str(width) + r'})\.(pack|idx|rev|bitmap|keep|promisor)', name)
                    if not match:
                        self.fail()
                    if match[2] not in ('pack', 'idx'):
                        continue
                elif not (re.fullmatch(r'[0-9a-f]{2}', level) and re.fullmatch(r'[0-9a-f]{' + str(width - 2) + r'}', name)):
                    self.fail()
                data, stamp = self.api.regular_bytes(fd, name, MAX_OBJECT_FILE_BYTES)
                if stamp != self.api.signature(info):
                    self.fail()
                self.bytes += len(data)
                if self.bytes > MAX_STORE_BYTES:
                    raise self.api.invalid('history_limit', 'History object bytes exceed comparison limits.')
                if level == 'pack':
                    if match[2] == 'pack':
                        if len(data) < 12 or data[:4] != b'PACK' or int.from_bytes(data[4:8], 'big') not in (2, 3):
                            self.fail()
                        pack_counts[match[1]] = int.from_bytes(data[8:12], 'big')
                    else:
                        offset = 8 if data[:4] == b'\xfftOc' else 0
                        if len(data) < offset + 1024 or (offset and data[4:8] != b'\x00\x00\x00\x02'):
                            self.fail()
                        counts = struct.unpack('>256I', data[offset:offset + 1024])
                        if any(a > b for a, b in zip(counts, counts[1:])):
                            self.fail()
                        index_counts[match[1]] = counts[-1]
                else:
                    self.objects += 1
                if self.objects + sum(pack_counts.values()) + sum(index_counts.values()) > MAX_OBJECTS * 2:
                    raise self.api.invalid('history_limit', 'History object count exceeds comparison limits.')
                (destination / name).write_bytes(data)
            if self.api.signature(os.fstat(fd)) != before:
                raise self.api.invalid('concurrent_change', 'Git objects changed while loading; refresh again.')
        objects = os.open('objects', flags, dir_fd=git_fd)
        try:
            destination = self.directory / 'objects'
            destination.mkdir()
            walk(objects, destination, 'objects')
        finally:
            os.close(objects)
        if pack_counts != index_counts:
            self.fail()
        if self.objects + sum(pack_counts.values()) > MAX_OBJECTS:
            raise self.api.invalid('history_limit', 'History object count exceeds comparison limits.')
        (self.directory / 'refs').mkdir()
        (self.directory / 'HEAD').write_text(head + '\n')
        config = '[core]\nrepositoryformatversion = ' + ('1' if width == 64 else '0') + '\nbare = true\n'
        if width == 64:
            config += '[extensions]\nobjectformat = sha256\n'
        (self.directory / 'config').write_text(config)

    def run(self, arguments, limit, input_data=b''):
        env = {'PATH': os.defpath, 'LC_ALL': 'C', 'LANG': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_SYSTEM': os.devnull,
               'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0',
               'GIT_ALLOW_PROTOCOL': ''}
        command = [self.git, '--no-replace-objects', '--literal-pathspecs', '--git-dir=' + str(self.directory), *arguments]
        self.remaining()
        with tempfile.TemporaryFile(dir=self.directory) as request:
            request.write(input_data)
            request.seek(0)
            process = subprocess.Popen(command, cwd=self.directory, env=env, stdin=request,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            chunks, count = [], 0
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while selector.get_map():
                        for key, _ in selector.select(min(.1, self.remaining())):
                            data = os.read(key.fileobj.fileno(), 65536)
                            if not data:
                                selector.unregister(key.fileobj)
                                continue
                            count += len(data)
                            if count > limit:
                                raise self.api.invalid('history_limit', 'Git output exceeds comparison limits.')
                            chunks.append(data)
                    code = process.wait(timeout=self.remaining())
                if code:
                    self.fail()
                return b''.join(chunks)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdout.close()

    def objects_data(self, identifiers, kind, per_file, total_limit):
        """Check declared uncompressed sizes before requesting any object contents."""
        unique = sorted(set(identifiers))
        request = ''.join(oid + '\n' for oid in unique).encode('ascii')
        checked = self.run(['cat-file', '--batch-check'], len(unique) * 100 + 1, request).decode('ascii').splitlines()
        sizes = {}
        if len(checked) != len(unique):
            self.fail()
        for expected, line in zip(unique, checked):
            oid, actual_kind, size = line.split()
            if oid != expected or actual_kind != kind or not size.isdigit():
                self.fail()
            sizes[oid] = int(size)
            if sizes[oid] > per_file:
                raise self.api.invalid('history_limit', 'History object bytes exceed comparison limits.')
        if sum(sizes.values()) > total_limit:
            raise self.api.invalid('history_limit', 'History object bytes exceed comparison limits.')
        payload = self.run(['cat-file', '--batch'], total_limit + len(unique) * 100, request)
        objects, cursor = {}, 0
        for expected in unique:
            end = payload.index(b'\n', cursor)
            header = payload[cursor:end].decode('ascii').split()
            if header != [expected, kind, str(sizes[expected])]:
                self.fail()
            cursor = end + 1
            objects[expected] = payload[cursor:cursor + sizes[expected]]
            cursor += sizes[expected]
            if payload[cursor:cursor + 1] != b'\n':
                self.fail()
            cursor += 1
        if cursor != len(payload):
            self.fail()
        return objects

    def commit_fields(self, data, width):
        headers = data.split(b'\n\n', 1)[0].split(b'\n')
        if not headers or not headers[0].startswith(b'tree '):
            self.fail()
        tree = headers[0][5:].decode('ascii')
        # Git parents are contiguous immediately after tree, not arbitrary later
        # extension headers. Reject ambiguity rather than broaden its ancestry.
        parents, index = [], 1
        while index < len(headers) and headers[index].startswith(b'parent '):
            parents.append(headers[index][7:].decode('ascii'))
            index += 1
        if any(line.startswith((b'tree ', b'parent ')) for line in headers[index:]):
            self.fail()
        if any(not SHA.fullmatch(value) or len(value) != width for value in [tree, *parents]):
            self.fail()
        return tree, parents

    def ancestors(self, head):
        pending, commits, total = {head}, {}, 0
        while pending:
            if len(commits) + len(pending) > MAX_COMMITS:
                raise self.api.invalid('history_limit', 'History commit count exceeds comparison limits.')
            objects = self.objects_data(pending, 'commit', MAX_COMMIT_BYTES, MAX_HISTORY_COMMIT_BYTES - total)
            total += sum(map(len, objects.values()))
            parents = set()
            for oid, data in objects.items():
                tree, links = self.commit_fields(data, len(head))
                commits[oid] = tree
                parents.update(links)
            pending = parents - commits.keys()
        return commits

    def tree_records(self, data, width):
        cursor = 0
        while cursor < len(data):
            end = data.index(b'\0', cursor)
            mode, raw_name = data[cursor:end].split(b' ', 1)
            oid = data[end + 1:end + 1 + width // 2]
            if len(oid) != width // 2:
                self.fail()
            cursor = end + 1 + width // 2
            yield mode.decode('ascii'), oid.hex(), raw_name.decode('utf-8')

    def snapshot(self, revision, root_tree):
        root_data = self.objects_data([root_tree], 'tree', MAX_TREE_BYTES, MAX_TREE_BYTES)[root_tree]
        top = [(mode, oid, name) for mode, oid, name in self.tree_records(root_data, len(revision)) if name in ('raw', 'wiki')]
        if len(top) != 2 or {item[2] for item in top} != {'raw', 'wiki'} or any(item[0] != '40000' for item in top):
            self.fail()
        pending = {folder: oid for _, oid, folder in top}
        entries, folded, count, total = {}, set(), 0, len(root_data)
        while pending:
            trees = self.objects_data(pending.values(), 'tree', MAX_TREE_BYTES, MAX_TREE_BYTES - total)
            total += sum(map(len, trees.values()))
            following = {}
            for folder, oid in pending.items():
                for mode, oid, name in self.tree_records(trees[oid], len(revision)):
                    count += 1
                    if count > self.api.MAX_DIRECTORY_ENTRIES:
                        raise self.api.invalid('history_limit', 'History tree exceeds comparison limits.')
                    path = folder + '/' + name
                    if path == 'wiki/log.md':
                        continue
                    self.api.canonical_reference(path)
                    if '/' in name or path.casefold() in folded or len(path.split('/')) > self.api.MAX_DEPTH + 2:
                        self.fail()
                    folded.add(path.casefold())
                    if mode == '40000':
                        following[path] = oid
                        continue
                    if mode not in ('100644', '100755') or not path.endswith('.md'):
                        self.fail()
                    entries[path] = oid
                    if len(entries) > self.api.MAX_NOTES:
                        raise self.api.invalid('history_limit', 'History note count exceeds comparison limits.')
            pending = following
        blobs = self.objects_data(entries.values(), 'blob', self.api.MAX_FILE_BYTES, self.api.MAX_TOTAL_BYTES)
        if sum(len(blobs[oid]) for oid in entries.values()) > self.api.MAX_TOTAL_BYTES:
            raise self.api.invalid('history_limit', 'History corpus bytes exceed comparison limits.')
        return {path: blobs[oid] for path, oid in entries.items()}


def delta(before, after, key, summarize):
    old, new = {key(item): item for item in before}, {key(item): item for item in after}
    return {'added': [summarize(new[k]) for k in sorted(new.keys() - old.keys())],
            'removed': [summarize(old[k]) for k in sorted(old.keys() - new.keys())],
            'changed': [{'id': k, 'before': summarize(old[k]), 'after': summarize(new[k]),
                         'fields': sorted(field for field in old[k].keys() | new[k].keys() if old[k].get(field) != new[k].get(field))}
                        for k in sorted(old.keys() & new.keys()) if old[k] != new[k]]}


def compare(root, base, target, api=None):
    if api is None:
        import viewer as api
    if not all(isinstance(value, str) and SHA.fullmatch(value) for value in (base, target)):
        raise api.invalid('invalid_revision', 'Provide exactly two full commit SHAs.')
    try:
        with api.directory_fd(root) as root_fd, tempfile.TemporaryDirectory(prefix='wiki-viewer-history-') as directory:
            identity = api.corpus_identity(root_fd)
            store = Store(api, directory)
            git_fd = os.open('.git', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                git_identity = api.corpus_identity(git_fd)
                head = store.head(git_fd)
                store.copy_objects(git_fd, head)
                ancestors = store.ancestors(head)
                if base not in ancestors or target not in ancestors:
                    raise api.invalid('invalid_revision', 'Both commits must belong to the current HEAD ancestry.')
                old = api.graph_from_inputs(store.snapshot(base, ancestors[base]), revision_id=base, corpus_id=identity)
                new = api.graph_from_inputs(store.snapshot(target, ancestors[target]), revision_id=target, corpus_id=identity)
                if store.head(git_fd) != head:
                    raise api.invalid('concurrent_change', 'Git HEAD changed while loading; refresh again.')
                api.check_identity(root, identity)
            finally:
                os.close(git_fd)
            summarize = lambda node: {key: node[key] for key in NODE_FIELDS}
            def edge_key(edge):
                value = {key: edge[key] for key in ('source', 'target', 'kind', 'provenance')}
                if 'record' in edge:
                    value['record'] = edge['record']
                return 'relation-' + hashlib.sha256(api.json_bytes(value)).hexdigest()
            nodes = delta(old['nodes'], new['nodes'], lambda node: node['id'], summarize)
            edges = delta(old['edges'], new['edges'], edge_key, lambda edge: edge)
            result = {'format': 1, 'base_revision': base, 'target_revision': target, 'head_revision': head,
                      'corpus_id': identity, 'nodes': nodes, 'edges': edges,
                      'stats': {name: {kind: len(values) for kind, values in change.items()} for name, change in (('nodes', nodes), ('edges', edges))},
                      'warnings': sorted(set(old['warnings'] + new['warnings'])),
                      'diagnostics': {'base': old['diagnostics'], 'target': new['diagnostics']}}
            if len(api.json_bytes(result)) > MAX_RESPONSE_BYTES:
                raise api.invalid('history_limit', 'Comparison response exceeds viewer limits.')
            # Reopen the named .git directory: checking only the held old FD would
            # miss a repository replacement within the same selected root inode.
            current = os.open('.git', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                if api.corpus_identity(current) != git_identity or store.head(current) != head:
                    raise api.invalid('concurrent_change', 'Git history changed while loading; refresh again.')
            finally:
                os.close(current)
            api.check_identity(root, identity)
            store.remaining()
            return result
    except api.ViewerError:
        raise
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError, KeyError, OverflowError, RecursionError, TypeError):
        raise api.invalid('invalid_history', 'History is unavailable or unsupported; no comparison was returned.') from None
