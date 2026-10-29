#!/usr/bin/env python3
"""Local Markdown knowledge tooling. No network, model calls, or dependencies."""
import argparse
from contextlib import contextmanager
import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import quote

OPERATIONS = {'ingest', 'review', 'maintain', 'query', 'index', 'lint'}
STATUSES = {'draft', 'reviewed', 'verified', 'deprecated', 'superseded'}
LINK = re.compile(r'(?<!\\)\[[^\]\n]*(?<!\\)\]\(([^)\n]+)\)')
# Authors write their own calendar date. Civil time zones run up to UTC+14, so a date one day
# after the current UTC date is still "today" somewhere (e.g. 00:00-06:59 in UTC+7).
MAX_DATE_AHEAD_OF_UTC = dt.timedelta(days=1)
# Metadata files that file managers create by themselves (Finder, Explorer, macOS on non-HFS
# volumes). They are never knowledge: local reads skip them; the Git hook refuses to commit them.
OS_METADATA_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}


def os_metadata(name):
    return name in OS_METADATA_FILES or name.startswith('._')


def git_bytes(root, *args):
    p = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
    if p.returncode:
        raise ValueError(p.stderr.decode('utf-8', errors='replace').strip() or 'Git operation failed')
    return p.stdout


def git(root, *args):
    return git_bytes(root, *args).decode('utf-8').strip()


def repo(root):
    if Path(git(root, 'rev-parse', '--show-toplevel')).resolve() != root.resolve():
        raise ValueError('Must target an initialized repository root')


def clean_guard(root):
    # Explicit flags defeat user ignoreSubmodules/status.showUntrackedFiles settings.
    if git(root, 'status', '--porcelain', '--untracked-files=all', '--ignore-submodules=none'):
        raise ValueError('Dirty tree: commit or preserve your changes first')
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        if Path(git(root, 'rev-parse', '--path-format=absolute', '--git-path', marker)).exists():
            raise ValueError('Git operation in progress: ' + marker)


def branch_guard(root, clean=False):
    repo(root)
    branch = git(root, 'symbolic-ref', '--quiet', '--short', 'HEAD')
    if not branch.startswith('contrib/'):
        raise ValueError('Use a contrib/ contribution branch/worktree, not main/master or another branch')
    if clean:
        clean_guard(root)


def inside(root, relative):
    """Check every lexical component before resolving, including internal symlinks."""
    if not isinstance(relative, str) or not relative or '\x00' in relative:
        raise ValueError('Expected a nonempty repository-relative path')
    if Path(relative).is_absolute():
        raise ValueError('Absolute paths are not allowed: ' + relative)
    current = root.resolve()
    for component in Path(relative).parts:
        if component == '..':
            current = current.parent
        else:
            current = current/component
        if not current.is_relative_to(root.resolve()):
            raise ValueError('Path escapes repository: ' + relative)
        if current.is_symlink():
            raise ValueError('Path contains a symlink: ' + relative)
    return current


def metadata_path(root, relative, prefix=None):
    if not isinstance(relative, str) or '..' in Path(relative).parts:
        raise ValueError('Metadata paths must be canonical repository-relative paths')
    p = inside(root, relative)
    if prefix and not p.is_relative_to(root.resolve()/prefix):
        raise ValueError('Path must be inside ' + prefix)
    if not p.is_file() or not stat.S_ISREG(p.stat().st_mode):
        raise ValueError('Missing regular file: ' + relative)
    return p


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def json_load(text):
    return json.loads(text, object_pairs_hook=object_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid JSON constant: ' + value)))


def read_page(p):
    text = p.read_text(encoding='utf-8')
    match = re.match(r'\A---json\n(.*?)\n---\n(.*)\Z', text, re.S)
    if not match:
        raise ValueError('Expected ---json metadata header')
    m = json_load(match[1])
    if not isinstance(m, dict):
        raise ValueError('Metadata must be an object')
    return m, match[2]


def inventory(root, folder):
    """No symlink traversal; unsupported files are explicit errors, not blind spots."""
    start = inside(root, folder)
    if not start.is_dir():
        raise ValueError('Missing directory: ' + folder)
    found = []
    def walk_error(error):
        raise error
    for current, dirs, files in os.walk(start, followlinks=False, onerror=walk_error):
        for name in dirs + files:
            path = Path(current)/name
            inside(root, str(path.relative_to(root.resolve())))
        for name in files:
            path = Path(current)/name
            if os_metadata(name) and stat.S_ISREG(path.stat().st_mode):
                continue
            if not stat.S_ISREG(path.stat().st_mode) or path.suffix != '.md':
                raise ValueError('Only regular Markdown files supported: ' + str(path.relative_to(root.resolve())))
            found.append(path)
    return sorted(found)


def pages(root):
    return [p for p in inventory(root, 'wiki') if p.relative_to(root.resolve()).as_posix() not in ('wiki/index.md', 'wiki/log.md')]


def inline(value):
    nonempty(value, 'index text')
    return value.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]').replace('\n', ' ').replace('\r', ' ')


def index_text(root):
    rows = ['# Wiki index', '', 'Generated navigation; edit page metadata, then run index.', '']
    for p in pages(root):
        m, _ = read_page(p)
        rows.append(f"- [{inline(m['title'])}]({quote(p.relative_to(root.resolve()/'wiki').as_posix())}) — {inline(m['summary'])} [{inline(m['status'])}]")
    return '\n'.join(rows) + '\n'


def nonempty(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing/invalid string: ' + field)


def strings(value, field, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError('Missing/nonempty list required: ' + field)
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError('Invalid list members: ' + field)
    if len(set(value)) != len(value):
        raise ValueError('Duplicate list members: ' + field)


def date(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Expected ISO date: ' + field)
    result = dt.date.fromisoformat(value)
    if result > dt.datetime.now(dt.timezone.utc).date() + MAX_DATE_AHEAD_OF_UTC:
        raise ValueError('Future date: ' + field)
    return result


def log_events(data):
    text = data.decode('utf-8')
    if not text.startswith('# Wiki log\n') or not text.endswith('\n'):
        raise ValueError('Invalid log header or missing final newline')
    # JSON strings may contain U+0085/U+2028/U+2029; only LF delimits events.
    events = [line + '\n' for line in text.split('\n')[1:-1]]
    for line in events:
        if not line.startswith('- ') or not line.endswith('\n'):
            raise ValueError('Invalid log event line')
        event = json_load(line[2:])
        if not isinstance(event, dict) or set(event) != {'at', 'operation', 'detail'}:
            raise ValueError('Invalid log event fields')
        if not isinstance(event['operation'], str) or event['operation'] not in OPERATIONS:
            raise ValueError('Invalid log operation')
        if not isinstance(event['at'], str):
            raise ValueError('Invalid log timestamp')
        stamp = dt.datetime.fromisoformat(event['at'])
        if stamp.tzinfo is None:
            raise ValueError('Log timestamp needs timezone')
    return events


@contextmanager
def mutation_lock(root):
    repo(root)
    path = Path(git(root, 'rev-parse', '--path-format=absolute', '--git-path', 'wiki-write.lock'))
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Another wiki writer or stale lock: ' + str(path)) from None
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def appended_log(root, operation, detail):
    if operation not in OPERATIONS:
        raise ValueError('Invalid operation')
    p = metadata_path(root, 'wiki/log.md')
    old = p.read_bytes()
    log_events(old)
    event = {'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'operation': operation, 'detail': detail}
    new = old + ('- ' + json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    log_events(new)
    return new


def atomic_write(path, data):
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            temp = Path(f.name)
            f.write(data)
        if path.exists():
            temp.chmod(stat.S_IMODE(path.stat().st_mode))
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def record(root, operation, detail):
    with mutation_lock(root):
        branch_guard(root)
        new = appended_log(root, operation, detail)
        atomic_write(inside(root, 'wiki/log.md'), new)


def history_check(root, revision, incoming=False):
    errors = []
    try:
        sha = git(root, 'rev-parse', '--verify', '--end-of-options', revision + '^{commit}')
        entries = git_bytes(root, 'ls-tree', '-rz', sha, '--', 'raw').split(b'\0')
        for entry in filter(None, entries):
            mode_info, path_bytes = entry.split(b'\t', 1)
            mode = mode_info.split()[0]
            rel = path_bytes.decode('utf-8')
            if mode not in (b'100644', b'100755'):
                errors.append('Baseline raw is not a regular file: ' + rel)
                continue
            old = git_bytes(root, 'show', sha + ':' + rel)
            if metadata_path(root, rel, 'raw').read_bytes() != old:
                errors.append('Immutable source changed: ' + rel)
        old_log = git_bytes(root, 'show', sha + ':wiki/log.md')
        old_events = log_events(old_log)
        new_log = metadata_path(root, 'wiki/log.md').read_bytes()
        if incoming:
            current_events = iter(log_events(new_log))
            for event in old_events:
                if not any(candidate == event for candidate in current_events):
                    errors.append('Incoming log event lost or reordered')
                    break
        elif not new_log.startswith(old_log):
            errors.append('Log is not append-only relative to baseline')
    except (ValueError, TypeError, OSError) as e:
        errors.append('History check: ' + str(e))
    return errors


def lint(root, base=None, merge_parent=None, check_index=True):
    root = root.resolve()
    errors, warnings, ids, sources, docs = [], [], set(), {}, {}
    try:
        raw_paths = inventory(root, 'raw')
        wiki_paths = inventory(root, 'wiki')
    except (ValueError, OSError) as e:
        return {'errors': [str(e)], 'warnings': [], 'history_checked': False}
    try:
        if (root/'.git').exists() and git(root, 'ls-files', '--unmerged'):
            errors.append('Unresolved Git index entries: resolve and stage the merge first')
    except ValueError as e:
        errors.append(str(e))
    for p in raw_paths:
        rel = p.relative_to(root).as_posix()
        try:
            sm, _ = read_page(p)
            for k in ('origin', 'collected_at', 'scope', 'version', 'permission'):
                nonempty(sm.get(k), k)
            date(sm['collected_at'], 'collected_at')
            if sm['scope'] != 'shared' or sm['permission'] not in ('synthetic-fixture', 'approved'):
                raise ValueError('Source not cleared for sharing')
            sources[rel] = sm
        except (ValueError, TypeError, OSError) as e:
            errors.append(rel + ': ' + str(e))
    for p in wiki_paths:
        label = p.relative_to(root).as_posix()
        if label in ('wiki/index.md', 'wiki/log.md'):
            continue
        try:
            m, body = read_page(p)
            if re.search(r'^(?:<{7}|={7}|>{7}|\|{7})(?: |$)', body, re.M):
                raise ValueError('Unresolved merge conflict markers in synthesized content')
            for k in ('id', 'title', 'summary', 'scope', 'status', 'updated_at'):
                nonempty(m.get(k), k)
            for k in ('tags', 'sources', 'applies_to'):
                strings(m.get(k), k)
            if not isinstance(m.get('claims'), list) or not m['claims']:
                raise ValueError('Missing/nonempty list required: claims')
            if m['scope'] != 'shared':
                raise ValueError('Project/session content is not allowed in shared wiki')
            if m['id'] in ids:
                raise ValueError('Duplicate id')
            ids.add(m['id'])
            if m['status'] not in STATUSES:
                raise ValueError('Invalid status')
            updated = date(m['updated_at'], 'updated_at')
            if (dt.datetime.now(dt.timezone.utc).date() - updated).days > 180:
                warnings.append(label + ': stale; review scope and evidence')
            if 'fixture' in m and not isinstance(m['fixture'], bool):
                raise ValueError('fixture must be boolean')
            if m['status'] in ('reviewed', 'verified') and not m.get('review_record'):
                raise ValueError('Review record required')
            for field in ('review_record', 'verification_evidence', 'superseded_by'):
                if field in m:
                    nonempty(m[field], field)
                    target = metadata_path(root, m[field], 'wiki' if field == 'superseded_by' else None)
                    if not target.read_bytes().strip():
                        raise ValueError('Empty ' + field)
                    if field == 'superseded_by' and (target == p or target.name in ('index.md', 'log.md')):
                        raise ValueError('Replacement must be another knowledge page')
            if m['status'] in ('superseded', 'deprecated') and not m.get('superseded_by'):
                raise ValueError('Replacement link required')
            for source in m['sources']:
                metadata_path(root, source, 'raw')
                if source not in sources:
                    raise ValueError('Invalid or noncanonical source: ' + source)
            synthetic = any(sources[s]['permission'] == 'synthetic-fixture' for s in m['sources'])
            if synthetic and m.get('fixture') is not True:
                raise ValueError('Synthetic sources require fixture: true')
            if m['status'] == 'verified':
                if m.get('fixture') or synthetic:
                    raise ValueError('Synthetic fixtures cannot be verified production knowledge')
                verified = date(m.get('verified_at'), 'verified_at')
                if (dt.datetime.now(dt.timezone.utc).date() - verified).days > 180:
                    warnings.append(label + ': stale verification evidence')
                if verified < updated or not m.get('verification_evidence'):
                    raise ValueError('Verification must cover latest updated_at and include evidence')
            for c in m['claims']:
                if not isinstance(c, dict) or c.get('kind') not in ('evidence', 'inference', 'unknown'):
                    raise ValueError('Claim requires explicit evidence/inference/unknown kind')
                nonempty(c.get('text'), 'claim text')
                strings(c.get('applies_to'), 'claim applies_to')
                strings(c.get('sources'), 'claim sources', allow_empty=True)
                if not set(c['applies_to']) <= set(m['applies_to']):
                    raise ValueError('Claim version must be in page applies_to')
                if not set(c['sources']) <= set(m['sources']):
                    raise ValueError('Claim source outside page sources')
                if c['kind'] == 'evidence':
                    if not c['sources']:
                        raise ValueError('Evidence requires source')
                    if not set(c['applies_to']) <= {sources[s]['version'] for s in c['sources']}:
                        raise ValueError('Evidence version not supported by cited source metadata')
            if not isinstance(m.get('contradictions', []), list):
                raise ValueError('Contradictions must be a list')
            for c in m.get('contradictions', []):
                if not isinstance(c, dict):
                    raise ValueError('Contradiction must be an object with source list')
                strings(c.get('sources'), 'contradiction sources')
                if c.get('status') not in ('open', 'resolved') or len(c['sources']) < 2 or not set(c['sources']) <= set(m['sources']):
                    raise ValueError('Invalid contradiction record')
                nonempty(c.get('resolution'), 'contradiction resolution')
                if c['status'] == 'open':
                    warnings.append(label + ': OPEN CONTRADICTION: ' + c['resolution'])
            if not any(target.split('#')[0].endswith('.md') for target in LINK.findall(body)):
                raise ValueError('Page needs a linked source or related page')
            docs[label] = m
        except (ValueError, KeyError, TypeError, OSError) as e:
            errors.append(label + ': ' + str(e))
    # Validate declared lineage as a graph, not merely file existence.
    for label, m in docs.items():
        if 'supersedes' in m:
            try:
                strings(m['supersedes'], 'supersedes')
                for old in m['supersedes']:
                    if old == label or old not in docs:
                        raise ValueError('supersedes must name another knowledge page')
            except ValueError as e:
                errors.append(label + ': ' + str(e))
        seen, current = {label}, m.get('superseded_by')
        while current:
            if current in seen or current not in docs:
                errors.append(label + ': replacement cycle or invalid knowledge page')
                break
            seen.add(current)
            current = docs[current].get('superseded_by')
    # MVP supports inline local file links only; external URLs/anchors are not verified.
    from urllib.parse import unquote
    for p in wiki_paths:
        rel = p.relative_to(root).as_posix()
        if rel == 'wiki/log.md' or (rel == 'wiki/index.md' and not check_index):
            continue
        try:
            content = p.read_text(encoding='utf-8') if rel == 'wiki/index.md' else read_page(p)[1]
            for target in LINK.findall(content):
                if '://' in target or target.startswith('#'):
                    continue
                relative = unquote(target.split('#')[0])
                if Path(relative).is_absolute():
                    raise ValueError('Absolute link path not allowed')
                dest = inside(root, str(p.parent.relative_to(root)/relative))
                if not dest.is_file():
                    errors.append(str(p.relative_to(root)) + ': broken link ' + target)
        except (OSError, ValueError) as e:
            errors.append(str(e))
    try:
        if check_index and metadata_path(root, 'wiki/index.md').read_text(encoding='utf-8') != index_text(root):
            errors.append('Index drift/orphan page: regenerate index')
        log_events(metadata_path(root, 'wiki/log.md').read_bytes())
    except (OSError, ValueError, KeyError, TypeError) as e:
        errors.append(str(e))
    if merge_parent and not base:
        errors.append('Merge parent requires first-parent baseline')
    history_errors = []
    if base:
        history_errors.extend(history_check(root, base))
        if merge_parent:
            history_errors.extend(history_check(root, merge_parent, incoming=True))
        errors.extend(history_errors)
    if not base:
        warnings.append('History not checked: supply a trusted --base commit')
    return {'errors': errors, 'warnings': warnings, 'history_checked': bool(base) and not history_errors}


def update_index(root):
    with mutation_lock(root):
        branch_guard(root)
        result = lint(root, check_index=False)
        if result['errors']:
            raise ValueError('Index blocked by lint: ' + '; '.join(result['errors']))
        path = inside(root, 'wiki/index.md')
        old_index = path.read_bytes() if path.exists() else None
        new_index = index_text(root).encode('utf-8')
        new_log = appended_log(root, 'index', 'Regenerated navigation')
        atomic_write(path, new_index)
        try:
            atomic_write(inside(root, 'wiki/log.md'), new_log)
        except OSError:
            if old_index is None:
                path.unlink()
            else:
                atomic_write(path, old_index)
            raise


def query(root, term, version, limit=5):
    nonempty(term, 'query term'); nonempty(version, 'query version')
    result = lint(root)
    if result['errors']:
        raise ValueError('Query blocked by lint: ' + '; '.join(result['errors']))
    found = []
    for p in pages(root):
        m, body = read_page(p)
        if m['status'] in ('deprecated', 'superseded') or version not in m['applies_to']:
            continue
        claims = [c for c in m['claims'] if version in c['applies_to']]
        searchable = ' '.join([m['title'], m['summary'], body, *m['tags'], *(c['text'] for c in claims)])
        if not claims or term.casefold() not in searchable.casefold():
            continue
        found.append({'page': str(p.relative_to(root.resolve())), 'status': m['status'], 'fixture': m.get('fixture', False), 'claims': claims, 'contradictions': m.get('contradictions', []), 'warnings': result['warnings'], 'validation': 'structural-only; history and semantic truth not established'})
    return found[:limit]


def pin(project, revision):
    with mutation_lock(project):
        clean_guard(project)
        git(project, 'symbolic-ref', '--quiet', 'HEAD')
        sub = inside(project, 'knowledge/shared')
        if not (sub/'.git').exists():
            raise ValueError('Submodule not initialized')
        repo(sub)
        entry = git(project, 'ls-files', '--stage', '--', 'knowledge/shared')
        if not entry.startswith('160000 ') or '\tknowledge/shared' not in entry:
            raise ValueError('Not a registered submodule')
        with mutation_lock(sub):
            clean_guard(sub)
            if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', revision):
                raise ValueError('Use a full local commit SHA')
            resolved = git(sub, 'rev-parse', '--verify', '--end-of-options', revision + '^{commit}')
            if resolved != revision:
                raise ValueError('SHA must identify a commit, not a tag object')
            # Ignored files are user work too: checkout must never overwrite them.
            git(sub, '-c', 'submodule.recurse=false', 'checkout', '--no-overwrite-ignore', '--detach', revision)
            return {'selected': revision, 'next': 'Review git diff, then commit project gitlink; no commit or fetch performed.'}


def create_worktree(root, path, branch):
    with mutation_lock(root):
        clean_guard(root)
        # Creating a new contribution branch from clean main/detached is safe.
        if not branch.startswith('contrib/'):
            raise ValueError('Use a contrib/ branch')
        git(root, 'check-ref-format', '--branch', branch)
        target = Path(os.path.abspath(path))
        if target.exists() or target.is_symlink() or target.is_relative_to(root.resolve()):
            raise ValueError('Use a new worktree path outside the source checkout')
        for part in [target, *target.parents]:
            if part.is_symlink():
                raise ValueError('Worktree destination contains a symlink')
        git(root, 'worktree', 'add', '-b', branch, str(target), 'HEAD')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    s = p.add_subparsers(dest='command', required=True)
    l = s.add_parser('lint'); l.add_argument('--base'); l.add_argument('--merge-parent'); l.add_argument('--record', action='store_true')
    s.add_parser('index')
    q = s.add_parser('query'); q.add_argument('term'); q.add_argument('--version', required=True); q.add_argument('--record', action='store_true')
    r = s.add_parser('record'); r.add_argument('operation', choices=['ingest', 'review', 'maintain', 'query']); r.add_argument('detail')
    w = s.add_parser('worktree'); w.add_argument('path', type=Path); w.add_argument('branch')
    u = s.add_parser('pin'); u.add_argument('sha')
    a = p.parse_args(); root = a.root.resolve()
    try:
        if a.command == 'lint':
            result = lint(root, a.base, a.merge_parent)
            if a.record: record(root, 'lint', result)
            print(json.dumps(result, indent=2)); return bool(result['errors'])
        if a.command == 'index': update_index(root)
        elif a.command == 'query':
            result = query(root, a.term, a.version)
            if a.record: record(root, 'query', {'term': a.term, 'version': a.version, 'pages': [r['page'] for r in result]})
            print(json.dumps(result, indent=2))
        elif a.command == 'record': record(root, a.operation, a.detail)
        elif a.command == 'worktree': create_worktree(root, a.path, a.branch)
        elif a.command == 'pin': print(json.dumps(pin(root, a.sha), indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as e:
        print('ERROR: ' + str(e), file=sys.stderr); return 2


if __name__ == '__main__':
    sys.exit(main())
