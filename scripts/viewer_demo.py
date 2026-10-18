#!/usr/bin/env python3
"""Create a separate SYNTHETIC DEMO wiki for local graph screenshots and benchmarks."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

import wiki


MAX_TOPICS = 200
LABEL = 'SYNTHETIC DEMO'


def write_note(path, metadata, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('---json\n' + json.dumps(metadata, ensure_ascii=False, indent=2)
                    + '\n---\n' + body, encoding='utf-8')


def new_destination(output):
    path = Path(output).absolute()
    # Inspect lexical ancestors before resolving: link/../new must not hide a link.
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('Demo destination must not contain symlinks')
    path = path.resolve()
    if path.exists():
        raise ValueError('Demo output must be a new directory; refusing to overwrite')
    if not path.parent.is_dir():
        raise ValueError('Demo output parent directory must already exist')
    return path


def generate(output, topics=8, *, as_of=None):
    """Generate six authored notes per topic; only the explicit date may vary."""
    if type(topics) is not int or not 1 <= topics <= MAX_TOPICS:
        raise ValueError('topics must be an integer from 1 to 200')
    day = (dt.datetime.now(dt.timezone.utc).date().isoformat()
           if as_of is None else as_of)
    wiki.date(day, 'demo date')
    root = new_destination(output)
    root.mkdir()  # Exclusive creation: never reuse an existing output directory.
    for number in range(1, topics + 1):
        topic = f'topic-{number:03d}'
        label = f'Topic {number:03d}'
        sources = [f'raw/{topic}/source-v{version}.md' for version in (1, 2)]
        versions = [f'SyntheticTopic{number:03d}/{version}' for version in (1, 2)]
        concept = f'wiki/concepts/{topic}'
        prior, current, comparison = [f'{concept}/{name}.md'
                                      for name in ('prior', 'current', 'comparison')]
        lesson = f'wiki/lessons/{topic}.md'
        capacity = [8 + 2 * (number - 1), 16 + 2 * (number - 1)]

        def evidence(index):
            return {'kind': 'evidence',
                    'text': f'{LABEL}: {label} capacity is {capacity[index]} in {versions[index]}.',
                    'sources': [sources[index]], 'applies_to': [versions[index]]}

        def page(name, title, source_list, version_list, claims, **extra):
            return dict(id=f'{topic}-{name}', title=f'{label}: {title} ({LABEL})',
                        summary=f'{LABEL} only: {title.lower()}; not production knowledge.',
                        scope='shared', tags=['synthetic-demo', topic], status='draft',
                        sources=source_list, applies_to=version_list, updated_at=day,
                        fixture=True, claims=claims, **extra)

        def body(title, text):
            return f'# {LABEL} — {label}: {title}\n\n' + (
                '> Invented fixture for viewer demonstrations only. No real project, '
                'measurement or production guidance.\n\n') + text + '\n'

        for index in (0, 1):
            meta = dict(title=f'{label}: source v{index + 1} ({LABEL})',
                        origin=f'synthetic:viewer-demo/{topic}/v{index + 1}',
                        collected_at=day, scope='shared', version=versions[index],
                        permission='synthetic-fixture', fixture=True,
                        tags=['synthetic-demo', topic])
            write_note(root / sources[index], meta, body(f'source v{index + 1}',
                       f'The fictional specification declares capacity **{capacity[index]}** '
                       f'for **{versions[index]}**. Values are invented; reproduction is permitted '
                       'because this source was generated for this synthetic demo.'))

        old_meta = page('prior', 'prior capacity', [sources[0]], [versions[0]],
                        [evidence(0)], superseded_by=current)
        old_meta['status'] = 'superseded'
        write_note(root / prior, old_meta, body('prior capacity',
                   f'[Source v1](../../../{sources[0]}) declares {capacity[0]} for {versions[0]}. '
                   '[Current page](current.md) supersedes this page for navigation; '
                   'the historical v1 evidence remains unchanged and version-scoped.'))

        write_note(root / current,
                   page('current', 'current capacity', [sources[1]], [versions[1]],
                        [evidence(1)], supersedes=[prior]),
                   body('current capacity',
                        f'[Source v2](../../../{sources[1]}) declares {capacity[1]} for {versions[1]}. '
                        'This page remains a draft, not verified knowledge. '
                        'See the [comparison](comparison.md) and '
                        f'[migration inference](../../lessons/{topic}.md).'))

        pending = (f'{LABEL}: capacities {capacity[0]} and {capacity[1]} disagree without a '
                   'version qualifier. Exact versions remain separate; compatibility and '
                   'migration behavior are unknown and require review. Newer does not mean verified.')
        write_note(root / comparison,
                   page('comparison', 'version comparison', sources, versions,
                        [evidence(0), evidence(1)], contradictions=[{
                            'status': 'open', 'sources': sources, 'resolution': pending}]),
                   body('version comparison',
                        f'**OPEN synthetic contradiction:** {pending}\n\n'
                        'Compare the [prior page](prior.md) with the [current page](current.md). '
                        'Neither source establishes behavior for the other version.'))

        inference = dict(kind='inference',
                         text=f'{LABEL}: migration may need a capacity check; this is an inference, not a measured result.',
                         sources=sources, applies_to=versions)
        lesson_text = ('**Inference only.** Preserve version boundaries when discussing the '
                       f'[comparison](../concepts/{topic}/comparison.md). No migration test '
                       'was performed, and no real-world conclusion follows from these fixtures.')
        # At most three explicit cross-topic links; no similarity-derived edges.
        if number <= min(3, topics - 1):
            lesson_text += (f'\n\nDemo-only cross-topic navigation: [next invented topic]'
                            f'(topic-{number + 1:03d}.md). This link is not evidence of a shared finding.')
        write_note(root / lesson, page('lesson', 'migration inference', sources,
                                      versions, [inference]), body('migration inference', lesson_text))

    (root / 'wiki/log.md').write_text('# Wiki log\n', encoding='utf-8')
    (root / 'wiki/index.md').write_text(wiki.index_text(root), encoding='utf-8')
    validation = wiki.lint(root)
    if validation['errors']:
        raise ValueError('Generated demo failed structural lint: ' + '; '.join(validation['errors']))
    return {'synthetic_demo': True, 'date': day, 'topics': topics,
            'authored_notes': 6 * topics, 'markdown_files': 6 * topics + 2,
            'expected_viewer_nodes': 6 * topics + 1,
            'explicit_cross_topic_links': min(3, topics - 1),
            'open_contradictions': topics, 'history_checked': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, metavar='NEW_DIRECTORY',
                        help='new standalone directory; parent must exist and contain no symlinks')
    parser.add_argument('--topics', type=int, default=8, metavar='N',
                        help='number of synthetic topics, 1–200 (default: 8)')
    parser.add_argument('--date', dest='as_of', metavar='YYYY-MM-DD',
                        help='explicit date for byte-reproducible fixtures; default: today in UTC')
    args = parser.parse_args()
    try:
        print(json.dumps(generate(args.output, args.topics, as_of=args.as_of), indent=2))
        return 0
    except (ValueError, OSError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
