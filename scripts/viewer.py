#!/usr/bin/env python3
"""Read-only, loopback-only graph viewer for canonical shared Markdown knowledge."""
import argparse
from bisect import bisect_right
from contextlib import contextmanager
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import posixpath
import re
import stat
import sys
import threading
from urllib.parse import quote, unquote, urlsplit

import wiki
from export_vault import prose_segments

FORMAT = 1
MAX_NOTES = 2000
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_DIRECTORY_ENTRIES = 8000
MAX_DEPTH = 24
MAX_EDGES = 20000
ASSET_ROOT = Path(__file__).resolve().parents[1] / 'viewer'
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
    '/vendor/cytoscape.min.js': ('vendor/cytoscape.min.js', 'text/javascript; charset=utf-8'),
    '/vendor/markdown-it.min.js': ('vendor/markdown-it.min.js', 'text/javascript; charset=utf-8'),
    '/vendor/purify.min.js': ('vendor/purify.min.js', 'text/javascript; charset=utf-8'),
}
CSP = ("default-src 'none'; script-src 'self'; style-src-elem 'self'; "
       "style-src-attr 'unsafe-inline'; img-src 'none'; connect-src 'self'; "
       "font-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
MARKDOWN_LINK = re.compile(r'(?<!!)(?<!\\)\[[^\]\n]*(?<!\\)\]\(([^)\n]+)\)')


class ViewerError(ValueError):
    """Public errors contain no source content, absolute paths, or OS error text."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def invalid(code='invalid_knowledge', message='Knowledge validation failed; no graph data was returned.'):
    return ViewerError(code, message)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


@contextmanager
def directory_fd(path):
    """Open every component without following symlinks; never resolve then reopen."""
    absolute = Path(os.path.abspath(path))
    if not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY'):
        raise invalid('unsupported_platform', 'This platform cannot provide confined reads.')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open('/', flags)
    try:
        for part in absolute.parts[1:]:
            new = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = new
        yield fd
    finally:
        os.close(fd)


def regular_bytes(parent_fd, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise invalid('unsafe_file', 'Only regular files are eligible for viewing.')
        if before.st_size > limit:
            raise invalid('limit_exceeded', 'Knowledge exceeds viewer size limits.')
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise invalid('limit_exceeded', 'Knowledge exceeds viewer size limits.')
        after = os.fstat(fd)
        if signature(before) != signature(after):
            raise invalid('concurrent_change', 'Knowledge changed while loading; refresh again.')
        return b''.join(chunks), signature(after)
    finally:
        os.close(fd)


def signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def scan(root_fd):
    """Read only raw/ and wiki/ through directory FDs. wiki/log.md is never opened."""
    result, stamps, counters = {}, {}, {'bytes': 0, 'entries': 0}
    def walk(parent, relative, depth):
        if depth > MAX_DEPTH:
            raise invalid('limit_exceeded', 'Knowledge exceeds viewer directory limits.')
        for name in sorted(os.listdir(parent)):
            rel = relative + '/' + name
            if rel == 'wiki/log.md':
                continue
            counters['entries'] += 1
            if counters['entries'] > MAX_DIRECTORY_ENTRIES:
                raise invalid('limit_exceeded', 'Knowledge exceeds viewer directory limits.')
            if name in ('.', '..') or '/' in name or '\\' in name or any(ord(c) < 32 for c in name):
                raise invalid('unsafe_path', 'Knowledge contains unsupported paths.')
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    if signature(os.fstat(child)) != signature(info):
                        raise invalid('concurrent_change', 'Knowledge changed while loading; refresh again.')
                    walk(child, rel, depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode) and name.endswith('.md'):
                if len(result) >= MAX_NOTES:
                    raise invalid('limit_exceeded', 'Knowledge exceeds viewer note limits.')
                data, stamp = regular_bytes(parent, name, MAX_FILE_BYTES)
                counters['bytes'] += len(data)
                if counters['bytes'] > MAX_TOTAL_BYTES:
                    raise invalid('limit_exceeded', 'Knowledge exceeds viewer size limits.')
                result[rel], stamps[rel] = data, stamp
            else:
                raise invalid('unsafe_file', 'Knowledge contains a symlink or unsupported file.')
    for folder in ('raw', 'wiki'):
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            walk(fd, folder, 0)
        finally:
            os.close(fd)
    return result, stamps


def read_snapshot(root):
    with directory_fd(root) as fd:
        first, before = scan(fd)
        second, after = scan(fd)
        if first != second or before != after:
            raise invalid('concurrent_change', 'Knowledge changed while loading; refresh again.')
    if 'wiki/index.md' not in first:
        raise invalid('missing_index', 'The canonical wiki index is missing.')
    return first, before


def parse_page(data):
    match = re.fullmatch(r'---json\n(.*?)\n---\n(.*)', data.decode('utf-8'), re.S)
    if not match:
        raise invalid()
    meta = wiki.json_load(match[1])
    if not isinstance(meta, dict):
        raise invalid()
    return meta, match[2]


def canonical_reference(value, prefix=None):
    wiki.nonempty(value, 'reference')
    if (value.startswith('/') or '\\' in value or any(ord(c) < 32 for c in value)
            or any(p in ('', '.', '..') or p.casefold() == '.git' for p in value.split('/'))
            or (prefix and not value.startswith(prefix + '/'))):
        raise invalid('unsafe_reference', 'Metadata contains an unsafe reference.')
    return value


def validate(documents):
    sources, pages, ids = {}, {}, set()
    warnings = ['Structural viewer checks only; factual truth, sharing rights, review files and Git history are not verified.']
    for path, (meta, body) in documents.items():
        if path == 'wiki/index.md':
            continue
        if path.startswith('raw/'):
            for key in ('origin', 'collected_at', 'scope', 'version', 'permission'):
                wiki.nonempty(meta.get(key), key)
            wiki.date(meta['collected_at'], 'collected_at')
            if meta['scope'] != 'shared' or meta['permission'] not in ('approved', 'synthetic-fixture'):
                raise invalid('private_scope', 'Knowledge is not cleared for shared viewing.')
            for field in ('title', 'summary'):
                if field in meta:
                    wiki.nonempty(meta[field], field)
            if 'tags' in meta:
                wiki.strings(meta['tags'], 'tags', allow_empty=True)
            sources[path] = meta
        else:
            for key in ('id', 'title', 'summary', 'scope', 'status', 'updated_at'):
                wiki.nonempty(meta.get(key), key)
            if meta['scope'] != 'shared':
                raise invalid('private_scope', 'Knowledge is not cleared for shared viewing.')
            if meta['id'] in ids or meta['status'] not in wiki.STATUSES:
                raise invalid()
            ids.add(meta['id'])
            for field in ('tags', 'sources', 'applies_to'):
                wiki.strings(meta.get(field), field)
            updated = wiki.date(meta['updated_at'], 'updated_at')
            if (dt.datetime.now(dt.timezone.utc).date() - updated).days > 180:
                warnings.append('A page is stale; review its scope and evidence.')
            if 'fixture' in meta and not isinstance(meta['fixture'], bool):
                raise invalid()
            if meta['status'] in ('reviewed', 'verified') and not meta.get('review_record'):
                raise invalid()
            for field in ('review_record', 'verification_evidence'):
                if field in meta:
                    canonical_reference(meta[field])  # Text only; never open referenced files.
            if meta['status'] == 'verified':
                verified = wiki.date(meta.get('verified_at'), 'verified_at')
                if verified < updated or not meta.get('verification_evidence') or meta.get('fixture'):
                    raise invalid()
            if meta['status'] in ('superseded', 'deprecated') and not meta.get('superseded_by'):
                raise invalid()
            if re.search(r'^(?:<{7}|={7}|>{7}|\|{7})(?: |$)', body, re.M):
                raise invalid('unresolved_conflict', 'Knowledge contains unresolved merge markers.')
            pages[path] = meta
    for path, meta in pages.items():
        for source in meta['sources']:
            canonical_reference(source, 'raw')
            if source not in sources:
                raise invalid('missing_source', 'Knowledge cites a source outside eligible shared notes.')
        synthetic = any(sources[s]['permission'] == 'synthetic-fixture' for s in meta['sources'])
        if synthetic and (meta.get('fixture') is not True or meta['status'] == 'verified'):
            raise invalid()
        claims = meta.get('claims')
        if not isinstance(claims, list) or not claims:
            raise invalid()
        for claim in claims:
            if not isinstance(claim, dict) or claim.get('kind') not in ('evidence', 'inference', 'unknown'):
                raise invalid()
            wiki.nonempty(claim.get('text'), 'claim text')
            wiki.strings(claim.get('sources'), 'claim sources', allow_empty=True)
            wiki.strings(claim.get('applies_to'), 'claim applies_to')
            if not set(claim['sources']) <= set(meta['sources']) or not set(claim['applies_to']) <= set(meta['applies_to']):
                raise invalid()
            if claim['kind'] == 'evidence' and (not claim['sources'] or not set(claim['applies_to']) <= {sources[s]['version'] for s in claim['sources']}):
                raise invalid()
        contradictions = meta.get('contradictions', [])
        if not isinstance(contradictions, list):
            raise invalid()
        for record in contradictions:
            if not isinstance(record, dict):
                raise invalid()
            wiki.strings(record.get('sources'), 'contradiction sources')
            wiki.nonempty(record.get('resolution'), 'resolution')
            if (len(record['sources']) < 2 or not set(record['sources']) <= set(meta['sources'])
                    or record.get('status') not in ('open', 'resolved')):
                raise invalid()
            if record['status'] == 'open':
                warnings.append('An explicit contradiction remains open.')
        if 'supersedes' in meta:
            wiki.strings(meta['supersedes'], 'supersedes')
            for target in meta['supersedes']:
                canonical_reference(target, 'wiki')
                if target == path or target not in pages:
                    raise invalid()
        seen, current = {path}, meta.get('superseded_by')
        while current:
            canonical_reference(current, 'wiki')
            if current in seen or current not in pages:
                raise invalid('invalid_lineage', 'Knowledge replacement links are invalid or cyclic.')
            seen.add(current)
            current = pages[current].get('superseded_by')
    expected_index = ['# Wiki index', '', 'Generated navigation; edit page metadata, then run index.', '']
    for path, meta in sorted(pages.items()):
        expected_index.append(f"- [{wiki.inline(meta['title'])}]({quote(path[len('wiki/'):])}) — {wiki.inline(meta['summary'])} [{wiki.inline(meta['status'])}]")
    if documents['wiki/index.md'][1] != '\n'.join(expected_index) + '\n':
        raise invalid('index_drift', 'The wiki index is stale; regenerate it through the canonical workflow.')
    return warnings


def local_link(source, target, eligible):
    try:
        parts = urlsplit(target)
        if parts.scheme or parts.netloc or parts.query or not parts.path:
            return None
        decoded = unquote(parts.path, errors='strict')
        if decoded.startswith('/') or '\\' in decoded or any(ord(c) < 32 for c in decoded):
            return None
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), decoded))
        return resolved if resolved in eligible else None
    except (ValueError, UnicodeError):
        return None


def prose_links(body):
    """Keep code-formatted labels, but exclude targets and links inside code."""
    protected, offset = [], 0
    for segment, is_code in prose_segments(body):
        if is_code:
            protected.append((offset, offset + len(segment)))
        offset += len(segment)
    starts = [start for start, _ in protected]
    def inside_code(position):
        index = bisect_right(starts, position) - 1
        return index >= 0 and position < protected[index][1]
    for match in MARKDOWN_LINK.finditer(body):
        positions = (match.start(), match.start(1), match.end(1) - 1, match.end() - 1)
        if not any(inside_code(position) for position in positions):
            yield match[1]


def relative_bytes(root_fd, path, limit):
    current = os.dup(root_fd)
    try:
        parts = path.split('/')
        for part in parts[:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = new
        return regular_bytes(current, parts[-1], limit)[0]
    finally:
        os.close(current)


def revision(root):
    """Read in-root HEAD metadata only; external gitfiles/configs are never opened."""
    try:
        with directory_fd(root) as root_fd:
            git_fd = os.open('.git', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                head = regular_bytes(git_fd, 'HEAD', 4096)[0].decode('ascii').strip()
                if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', head):
                    return head
                if not head.startswith('ref: refs/'):
                    return None
                ref = head[5:]
                canonical_reference(ref, 'refs')
                try:
                    value = relative_bytes(git_fd, ref, 4096).decode('ascii').strip()
                except FileNotFoundError:
                    packed = regular_bytes(git_fd, 'packed-refs', MAX_FILE_BYTES)[0].decode('ascii')
                    value = next((line.split(' ', 1)[0] for line in packed.splitlines()
                                  if line.endswith(' ' + ref)), '')
                return value if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', value) else None
            finally:
                os.close(git_fd)
    except (OSError, UnicodeError, ValueError):
        return None


def build_graph(root):
    try:
        inputs, stamps = read_snapshot(root)
        documents = {path: ({}, data.decode('utf-8')) if path == 'wiki/index.md' else parse_page(data)
                     for path, data in sorted(inputs.items())}
        warnings = validate(documents)
        nodes, edge_map = [], {}
        def edge(source, target, kind, section, **extra):
            value = dict(source=source, target=target, kind=kind, explicit=True,
                         provenance={'file': source, 'section': section}, **extra)
            key = hashlib.sha256(json_bytes(value)).hexdigest()
            if key not in edge_map and len(edge_map) >= MAX_EDGES:
                raise invalid('limit_exceeded', 'Knowledge exceeds viewer relationship limits.')
            edge_map[key] = {'id': 'edge-' + key, **value}
        for path, (meta, body) in documents.items():
            kind = ('navigation' if path == 'wiki/index.md' else 'source' if path.startswith('raw/')
                    else 'concept' if path.startswith('wiki/concepts/') else 'lesson' if path.startswith('wiki/lessons/') else 'page')
            node = {'id': path, 'title': meta.get('title', 'Wiki index' if kind == 'navigation' else meta.get('origin', Path(path).stem)),
                    'kind': kind, 'summary': meta.get('summary', ''), 'status': 'source' if kind == 'source' else meta.get('status', 'navigation'),
                    'fixture': (meta.get('permission') == 'synthetic-fixture' or meta.get('fixture') is True) if kind == 'source' else meta.get('fixture', False),
                    'scope': meta.get('scope', 'shared'), 'tags': meta.get('tags', []),
                    'applies_to': [meta['version']] if kind == 'source' else meta.get('applies_to', []),
                    'body': body, 'metadata': meta}
            nodes.append(node)
            for href in prose_links(body):
                target = local_link(path, href, documents)
                if target:
                    edge(path, target, 'link', 'body')
            for target in meta.get('sources', []) if kind != 'source' else []:
                edge(path, target, 'sources', 'metadata.sources')
            for number, claim in enumerate(meta.get('claims', []) if kind != 'source' else []):
                for target in claim['sources']:
                    edge(path, target, 'claim', f'metadata.claims[{number}].sources', record=number, claim_kind=claim['kind'])
            for number, record in enumerate(meta.get('contradictions', []) if kind != 'source' else []):
                for target in record['sources']:
                    edge(path, target, 'contradiction', f'metadata.contradictions[{number}].sources', record=number, status=record['status'])
            for target in meta.get('supersedes', []) if kind != 'source' else []:
                edge(path, target, 'supersedes', 'metadata.supersedes')
            if kind != 'source' and meta.get('superseded_by'):
                edge(path, meta['superseded_by'], 'superseded_by', 'metadata.superseded_by')
        source_digest = hashlib.sha256(json_bytes({name: hashlib.sha256(data).hexdigest() for name, data in sorted(inputs.items())})).hexdigest()
        edges = [edge_map[key] for key in sorted(edge_map)]
        return {'format': FORMAT, 'source_digest': source_digest, 'nodes': nodes, 'edges': edges,
                'warnings': sorted(set(warnings)), 'stats': {'nodes': len(nodes), 'edges': len(edges)},
                'snapshot': {'revision': revision(root), 'index_updated_at': dt.datetime.fromtimestamp(stamps['wiki/index.md'][4] / 1e9, dt.timezone.utc).isoformat(),
                             'loaded_at': dt.datetime.now(dt.timezone.utc).isoformat()}}
    except ViewerError:
        raise
    except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError):
        raise invalid() from None


def asset_bytes(relative):
    with directory_fd(ASSET_ROOT) as fd:
        parts = relative.split('/')
        current = os.dup(fd)
        try:
            for part in parts[:-1]:
                new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                os.close(current)
                current = new
            return regular_bytes(current, parts[-1], 4 * 1024 * 1024)[0]
        finally:
            os.close(current)


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = 'WikiViewer'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass  # Request paths and source-derived strings never enter access logs.

    def respond(self, code, data, content_type='application/json; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def fail(self, status, code, message):
        self.respond(status, json_bytes({'error': {'code': code, 'message': message}}))

    def send_error(self, code, message=None, explain=None):
        self.fail(code, 'invalid_request', 'Request rejected.')

    def allowed(self):
        authority = '127.0.0.1:' + str(self.server.server_port)
        hosts = self.headers.get_all('Host', [])
        origins = self.headers.get_all('Origin', [])
        sites = self.headers.get_all('Sec-Fetch-Site', [])
        if (hosts != [authority] or (origins and origins != ['http://' + authority])
                or (sites and (len(sites) != 1 or sites[0] not in ('same-origin', 'none')))):
            self.fail(403, 'forbidden_origin', 'Only same-origin loopback requests are accepted.')
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        try:
            parts = urlsplit(self.path)
            if parts.scheme or parts.netloc or '%' in parts.path or parts.fragment:
                self.fail(404, 'not_found', 'Resource not found.')
                return
            path = parts.path
            if path == '/api/graph':
                if not self.server.graph_slots.acquire(blocking=False):
                    self.fail(503, 'busy', 'The viewer is loading another snapshot; retry shortly.')
                    return
                try:
                    result = build_graph(self.server.knowledge_root)
                    self.respond(200, json_bytes(result))
                finally:
                    self.server.graph_slots.release()
            elif path in ASSETS:
                relative, content_type = ASSETS[path]
                self.respond(200, asset_bytes(relative), content_type)
            else:
                self.fail(404, 'not_found', 'Resource not found.')
        except ViewerError as error:
            self.fail(409 if error.code == 'concurrent_change' else 422, error.code, str(error))
        except (OSError, ValueError):
            self.fail(503, 'unavailable', 'The requested viewer resource is unavailable.')

    do_HEAD = do_GET

    def reject_method(self):
        if self.allowed():
            self.fail(405, 'read_only', 'This viewer only accepts GET and HEAD requests.')

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = reject_method


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, root, port):
        self.knowledge_root = Path(os.path.abspath(root))
        self.graph_slots = threading.BoundedSemaphore(1)
        super().__init__(('127.0.0.1', port), ViewerHandler)


def create_server(root, port=8765):
    return ViewerServer(root, port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--check', action='store_true', help='validate a snapshot and print its summary without starting HTTP')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    try:
        if args.check:
            graph = build_graph(args.root)
            print(json.dumps({key: graph[key] for key in ('format', 'source_digest', 'stats', 'snapshot', 'warnings')}, indent=2))
            return 0
        with create_server(args.root, args.port) as server:
            print(f'Local read-only viewer: http://127.0.0.1:{server.server_port}/', flush=True)
            server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except ViewerError as error:
        print('Viewer ERROR: ' + str(error), file=sys.stderr)
        return 2
    except OSError:
        print('Viewer ERROR: Unable to start the local viewer.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
