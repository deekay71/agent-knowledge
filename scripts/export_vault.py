#!/usr/bin/env python3
"""Export a portable Markdown vault without modifying canonical knowledge."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import quote, unquote, urlsplit

import wiki

FORMAT = 1
MANIFEST = '.vault-manifest.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def portable_name(name):
    # These filenames must behave the same on macOS, Windows and in Obsidian.
    for part in name.split('/'):
        if (not part or part in ('.', '..') or part.endswith((' ', '.'))
                or re.search(r'[\x00-\x1f<>:"\\|?*#^\[\]%]', part)
                or part.casefold() in ('.git', '.obsidian')
                or part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
            raise ValueError('Filename is not portable to a Markdown vault: ' + name)


def scalar(value):
    # JSON quoted strings/booleans/numbers are also YAML scalars. Escape YAML
    # line-separator characters rather than allowing the parser to fold them.
    return json.dumps(value, ensure_ascii=True, allow_nan=False)


def frontmatter(properties):
    rows = ['---']
    for key, value in properties.items():
        if not re.fullmatch(r'[a-z][a-z0-9_]*', key):
            continue
        if isinstance(value, list) and all(isinstance(x, (str, bool, int, float)) for x in value):
            rows.append(key + ':' if value else key + ': []')
            rows.extend('  - ' + scalar(x) for x in value)
        elif isinstance(value, (str, bool, int, float)):
            rows.append(key + ': ' + scalar(value))
    return '\n'.join(rows + ['---', '']) + '\n'


def text(value):
    """Render metadata as text, never HTML, Markdown instructions or extra links."""
    value = str(value).replace('&', '&amp;').replace('\n', ' ').replace('\r', ' ')
    return re.sub(r'([\\`*_{}\[\]()<>#!|])', r'\\\1', value)


def link(page, target, label=None):
    rel = os.path.relpath(target, str(Path(page).parent)).replace(os.sep, '/')
    return '[' + text(label or target) + '](' + quote(rel, safe='/.-_~') + ')'


def input_files(root):
    paths = wiki.inventory(root, 'raw') + wiki.inventory(root, 'wiki')
    # Review/verification notes may live outside wiki/. Only explicitly referenced
    # Markdown is copied; no recursive copying of project files or attachments.
    for page in wiki.pages(root):
        meta, _ = wiki.read_page(page)
        for field in ('review_record', 'verification_evidence'):
            if field in meta:
                target = wiki.metadata_path(root, meta[field])
                if target.suffix != '.md':
                    raise ValueError('Vault requires Markdown ' + field + ': ' + meta[field])
                paths.append(target)
    result, folded = {}, set()
    for path in sorted(set(paths)):
        name = path.relative_to(root).as_posix()
        portable_name(name)
        if name.casefold() == 'home.md' or name.split('/')[0].casefold() == 'vault':
            raise ValueError('Input collides with the generated vault: ' + name)
        if name.casefold() in folded:
            raise ValueError('Case-colliding vault input: ' + name)
        folded.add(name.casefold())
        result[name] = path.read_bytes()
    return result


def input_digest(inputs):
    return digest(json_bytes({name: digest(data) for name, data in sorted(inputs.items())}))


def prose_segments(body):
    """Yield (text, is_code) without interpreting fenced or inline code as links.

    Support CommonMark backtick/tilde fences and exact-length backtick spans.
    Preserve every literal byte; reject an unclosed fence before appending metadata.
    """
    fence = None
    prose = []
    def inline_segments(chunk):
        cursor = 0
        while cursor < len(chunk):
            opening = re.search(r'(?<![\\`])(`+)', chunk[cursor:])
            if not opening:
                yield chunk[cursor:], False
                return
            start = cursor + opening.start()
            end = cursor + opening.end()
            closing = re.search(r'(?<!`)' + re.escape(opening[1]) + r'(?!`)', chunk[end:])
            if not closing:
                # An unmatched backtick is literal prose, not a code span.
                yield chunk[cursor:end], False
                cursor = end
                continue
            yield chunk[cursor:start], False
            finish = end + closing.end()
            yield chunk[start:finish], True
            cursor = finish
    for line in body.splitlines(keepends=True):
        if fence:
            yield line, True
            if re.fullmatch(r' {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}[ \t]*\r?\n?', line):
                fence = None
            continue
        opening = re.match(r' {0,3}(`{3,}|~{3,})(.*)', line)
        if opening and not (opening[1][0] == '`' and '`' in opening[2]):
            yield from inline_segments(''.join(prose))
            prose = []
            fence = opening[1]
            yield line, True
        elif line.startswith(('    ', '\t')) and (not prose or not prose[-1].strip()):
            # Indented code blocks at paragraph boundaries. Nested-list links use
            # the inline Markdown contract and are not treated as code here.
            yield from inline_segments(''.join(prose))
            prose = []
            yield line, True
        else:
            prose.append(line)
    if fence:
        raise ValueError('Unclosed fenced code block; close it before exporting metadata')
    yield from inline_segments(''.join(prose))


def normalize_links(name, body, inputs, edges):
    def replace(match):
        target = match[1]
        parts = urlsplit(target)
        if parts.scheme:
            if parts.scheme.lower() not in ('http', 'https', 'mailto'):
                raise ValueError('Unsupported link scheme in ' + name + ': ' + parts.scheme)
            return match[0]
        if parts.netloc or parts.query:
            raise ValueError('Unsupported local link in ' + name + ': ' + target)
        if not parts.path:
            return match[0]  # a same-note heading, not a graph edge
        decoded = unquote(parts.path)
        if decoded.startswith('/') or '\\' in decoded:
            raise ValueError('Absolute/nonportable local link in ' + name)
        dest = os.path.normpath(str(Path(name).parent / decoded)).replace(os.sep, '/')
        if dest not in inputs:
            raise ValueError('Link target is outside the exported notes: ' + name + ' -> ' + dest)
        edges.append({'from': name, 'to': dest, 'kind': 'link'})
        path = quote(os.path.relpath(dest, str(Path(name).parent)).replace(os.sep, '/'), safe='/.-_~')
        if parts.fragment:
            path += '#' + quote(unquote(parts.fragment), safe='-._~')
        return match[0][:match.start(1) - match.start()] + path + ')'
    return ''.join(segment if is_code else wiki.LINK.sub(replace, segment)
                   for segment, is_code in prose_segments(body))


def build(root):
    root = Path(root).resolve()
    result = wiki.lint(root)
    if result['errors']:
        raise ValueError('Vault export blocked by lint: ' + '; '.join(result['errors']))
    inputs = input_files(root)
    fingerprint = input_digest(inputs)
    files, nodes, edges = {}, [], []
    for name, data in inputs.items():
        special = name in ('wiki/index.md', 'wiki/log.md')
        kind = 'navigation' if special else 'source' if name.startswith('raw/') else 'wiki' if name.startswith('wiki/') else 'review'
        if special or kind == 'review':
            meta, body = {}, data.decode('utf-8')
        else:
            meta, body = wiki.read_page(root/name)
        properties = {k: v for k, v in meta.items() if k not in ('claims', 'contradictions')}
        properties.update(generated=True, canonical_path=name, source_sha256=digest(data), note_type=kind)
        # A path string property is not necessarily a graph link. Render explicit
        # Markdown links in the body for every metadata relationship below.
        title = meta.get('title', Path(name).stem)
        nodes.append({'id': name, 'title': title, 'kind': kind, 'status': meta.get('status'), 'fixture': meta.get('fixture', meta.get('permission') == 'synthetic-fixture')})
        rendered = frontmatter(properties)
        rendered += '> Generated reading view. Edit the canonical repository file, then export again.\n\n'
        if kind == 'source':
            rendered += '> Source projection; canonical raw bytes are preserved in the repository.\n\n'
        # The log contains JSON data that might include bracket syntax. Present it
        # literally and never interpret event details as links or executable HTML.
        if name == 'wiki/log.md':
            fence = '`' * max(3, max((len(x) + 1 for x in re.findall(r'`+', body)), default=3))
            rendered += '# Wiki log\n\n' + fence + 'text\n' + body + fence + '\n'
        else:
            rendered += normalize_links(name, body, inputs, edges).rstrip() + '\n'
        if meta:
            rendered += '\n## Knowledge metadata\n\n'
            if meta.get('fixture') or meta.get('permission') == 'synthetic-fixture':
                rendered += '**Synthetic fixture — not production guidance.**\n\n'
            for key in ('status', 'scope', 'version', 'applies_to', 'origin', 'collected_at', 'permission', 'updated_at', 'verified_at'):
                if key in meta:
                    value = ', '.join(meta[key]) if isinstance(meta[key], list) else meta[key]
                    rendered += '- **' + key + ':** ' + text(value) + '\n'
            def relationship(target, relation, extra=None):
                if target not in inputs:
                    raise ValueError('Relationship outside exported notes: ' + target)
                edge = {'from': name, 'to': target, 'kind': relation}
                if extra:
                    edge.update(extra)
                edges.append(edge)
                return link(name, target)
            for key in ('sources', 'supersedes', 'superseded_by', 'review_record', 'verification_evidence'):
                if key in meta:
                    values = meta[key] if isinstance(meta[key], list) else [meta[key]]
                    rendered += '\n**' + key + ':**\n\n'
                    rendered += ''.join('- ' + relationship(target, key) + '\n' for target in values)
            if meta.get('claims'):
                rendered += '\n## Authored claims\n\n'
                for claim in meta['claims']:
                    rendered += '- **' + claim['kind'] + '** — ' + text(claim['text']) + '\n'
                    rendered += '  - Applies to: ' + text(', '.join(claim['applies_to'])) + '\n'
                    rendered += '  - Sources: ' + (', '.join(relationship(s, 'claim', {'claim_kind': claim['kind']}) for s in claim['sources']) or 'none; unknown') + '\n'
            if meta.get('contradictions'):
                rendered += '\n## Declared contradictions\n\n'
                for number, conflict in enumerate(meta['contradictions'], 1):
                    rendered += '- **' + conflict['status'].upper() + '** — ' + text(conflict['resolution']) + '\n'
                    rendered += '  - Evidence: ' + ', '.join(relationship(s, 'contradiction', {'status': conflict['status'], 'record': number}) for s in conflict['sources']) + '\n'
        files[name] = rendered.encode('utf-8')
    home = frontmatter({'title': 'Agent Knowledge', 'generated': True, 'note_type': 'navigation'})
    home += '# Agent Knowledge\n\nA portable reading view of the shared wiki. Current starter content is synthetic fixtures, not production guidance.\n\n'
    home += 'Open this folder as an Obsidian vault, then open **Graph view**. Nodes are notes; lines are internal links.\n\n'
    home += '## Browse\n\n'
    home += '- [Wiki index](wiki/index.md)\n- [Operation log](wiki/log.md)\n\n'
    for node in nodes:
        if node['kind'] != 'navigation':
            home += '- ' + link('Home.md', node['id'], node['title']) + ' — ' + node['kind'] + '\n'
    home += '\n## Reading and maintenance\n\n'
    home += 'Check exact versions and evidence/inference/unknown labels. A graph connection is not a claim of correctness. Open contradictions remain visible in their notes.\n\n'
    home += 'This is a generated view, with no bidirectional sync. Edit canonical raw/wiki files through the repository contribution workflow. Never edit an archived raw source; add a new version. Refresh using `python3 scripts/export_vault.py --refresh` from the repository root. Local edits here block refresh and must be preserved separately first.\n\n'
    home += 'Obsidian settings in `.obsidian/` remain local. No plugins, network service or account is required by the exporter. Other Markdown readers can follow relative links; graph/properties support depends on the app.\n\n'
    home += 'For a focused graph, filter out `Home`, `wiki/index` and `wiki/log`. Native graph edges are untyped; `graph.json` retains relationship types for other tools.\n'
    files['Home.md'] = home.encode('utf-8')
    edges += [{'from': 'Home.md', 'to': node['id'], 'kind': 'navigation'} for node in nodes]
    nodes.append({'id': 'Home.md', 'title': 'Agent Knowledge', 'kind': 'navigation', 'status': None, 'fixture': False})
    unique_edges = {json.dumps(edge, sort_keys=True): edge for edge in edges}
    files['graph.json'] = json_bytes({'format': FORMAT, 'source_digest': fingerprint, 'nodes': nodes, 'edges': [unique_edges[k] for k in sorted(unique_edges)]})
    files[MANIFEST] = json_bytes({'format': FORMAT, 'generator': 'agent-knowledge/export_vault', 'source_digest': fingerprint, 'inputs': {n: digest(d) for n, d in inputs.items()}, 'files': {n: digest(d) for n, d in sorted(files.items())}})
    # Detect an editor changing source while the projection was being compiled.
    if input_files(root) != inputs:
        raise ValueError('Knowledge changed during export; retry after writers finish')
    return files


def destination(root, output):
    root = Path(root).resolve()
    output = Path(os.path.abspath(output))
    if output.is_symlink():
        raise ValueError('Vault destination must not be a symlink')
    output = output.resolve()
    if output != root/'vault' and (output.is_relative_to(root) or root.is_relative_to(output)):
        raise ValueError('Use repo/vault or a separate directory outside the repository')
    if not output.parent.is_dir():
        raise ValueError('Vault parent directory must already exist')
    return output


def existing_files(output):
    if not output.is_dir():
        raise ValueError('Vault directory does not exist')
    found = {}
    def walk_error(error):
        raise error
    for current, dirs, names in os.walk(output, followlinks=False, onerror=walk_error):
        for name in dirs + names:
            path = Path(current)/name
            if path.is_symlink():
                raise ValueError('Symlink in vault: ' + path.relative_to(output).as_posix())
        # App preferences are never read, copied, executed, overwritten or deleted.
        if Path(current) == output and '.obsidian' in dirs:
            dirs.remove('.obsidian')
        for name in names:
            path = Path(current)/name
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError('Nonregular vault file: ' + name)
            if wiki.os_metadata(name):
                continue  # Finder/Explorer metadata: not managed, never compared or deleted.
            found[path.relative_to(output).as_posix()] = path.read_bytes()
    return found


def check(root, output):
    output = destination(root, output)
    expected = build(root)
    actual = existing_files(output)
    if actual != expected:
        changed = sorted(n for n in actual.keys() | expected.keys() if actual.get(n) != expected.get(n))
        raise ValueError('Vault drift: regenerate and stage the view; changed/missing/unexpected: ' + ', '.join(changed))
    manifest = wiki.json_load(expected[MANIFEST].decode())
    return {'files': len(expected), 'source_digest': manifest['source_digest'], 'validation': 'deterministic Markdown projection; GUI not tested'}


@contextmanager
def output_lock(output):
    lock = output.parent/('.' + output.name + '.export.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Another exporter or stale lock: ' + str(lock)) from None
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink()


def export(root, output, refresh=False):
    output = destination(root, output)
    with output_lock(output):
        files = build(root)
        if not output.exists():
            with tempfile.TemporaryDirectory(prefix='.vault-build-', dir=output.parent) as temp:
                staging = Path(temp)/'vault'
                staging.mkdir()
                for name, data in files.items():
                    target = staging/name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                staging.rename(output)
        else:
            if not refresh:
                raise ValueError('Vault already exists; use --check or --refresh')
            old = existing_files(output)
            if MANIFEST not in old:
                raise ValueError('Refusing to replace an unmanaged directory')
            manifest = wiki.json_load(old[MANIFEST].decode('utf-8'))
            if (not isinstance(manifest, dict) or manifest.get('format') != FORMAT
                    or manifest.get('generator') != 'agent-knowledge/export_vault'
                    or not isinstance(manifest.get('files'), dict)):
                raise ValueError('Unrecognized vault manifest')
            actual_hashes = {n: digest(d) for n, d in old.items() if n != MANIFEST}
            if actual_hashes != manifest['files']:
                raise ValueError('Local edits or unknown files in vault; preserve them before refreshing')
            old_parents = {str(p) for n in old for p in Path(n).parents if str(p) != '.'}
            new_parents = {str(p) for n in files for p in Path(n).parents if str(p) != '.'}
            if old.keys() & new_parents or files.keys() & old_parents:
                raise ValueError('File/directory shape changed; export to a new directory to preserve the old view')
            for name in files:
                target = wiki.inside(output, name)
                if target.is_dir():
                    raise ValueError('Directory occupies a generated filename: ' + name)
            # Preflight all edits before writing. Roll back ordinary I/O failures;
            # this is not a multi-file power-loss transaction or an editor lock.
            touched = []
            try:
                for name in sorted(files.keys() | old.keys(), key=lambda n: (n == MANIFEST, n)):
                    if files.get(name) == old.get(name):
                        continue
                    target = output/name
                    touched.append(name)
                    if name in files:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        wiki.atomic_write(target, files[name])
                    else:
                        target.unlink()
            except OSError:
                for name in reversed(touched):
                    target = output/name
                    if name in old:
                        wiki.atomic_write(target, old[name])
                    elif target.is_file():
                        target.unlink()
                raise
    return {'files': len(files), 'source_digest': wiki.json_load(files[MANIFEST].decode())['source_digest'], 'output': str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, help='default: ROOT/vault; otherwise a separate directory')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='read-only drift check')
    mode.add_argument('--refresh', action='store_true', help='refresh an unchanged managed vault')
    args = parser.parse_args()
    try:
        output = args.output or args.root/'vault'
        result = check(args.root, output) if args.check else export(args.root, output, args.refresh)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError) as error:
        print('Vault ERROR: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
