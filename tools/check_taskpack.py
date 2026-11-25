#!/usr/bin/env python3
"""Validate this task pack's structure and synthetic assets; does not test the plugin."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
import sys
from collections import Counter

try:
    import tomllib
except ImportError:
    raise SystemExit('This task-pack checker requires Python 3.11+ (implementation target: 3.12).')


ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {'implementation', '.git', '__pycache__', '.pytest_cache', '.venv'}
errors: list[str] = []


def is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.relative_to(ROOT).parts)


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        errors.append(f'{path.relative_to(ROOT)}: {exc}')
        return None


def main() -> int:
    required = [
        'README.md', 'START_HERE.md', 'AGENTS.md', 'MASTER_TASK.md',
        'docs/00-scope.md', 'docs/10-architecture.md', 'docs/20-maibot-contract.md',
        'docs/30-openai-contract.md', 'docs/40-credentials-and-concurrency.md',
        'docs/45-errors-and-retries.md', 'docs/50-test-plan.md', 'docs/60-docker-runbook.md',
        'docs/70-release-and-handoff.md', 'docs/80-future-roadmap.md',
        'tasks/BACKLOG.md', 'tasks/backlog.json', 'acceptance/test-matrix.csv',
        'acceptance/REPORT_TEMPLATE.md', 'examples/model_catalog.fragment.toml',
        'examples/plugin-config.target.toml', 'examples/credentials.schema.example.json', 'fixtures/README.md',
        'references/SOURCES.md', 'references/compatibility-baseline.json',
        'TASKPACK_MANIFEST.json',
    ]
    for relative in required:
        check((ROOT / relative).is_file(), f'Missing: {relative}')
    for path in ROOT.rglob('*.json'):
        if is_ignored(path):
            continue
        read_json(path)
    for path in ROOT.rglob('*.toml'):
        if is_ignored(path):
            continue
        try:
            tomllib.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            errors.append(f'Invalid TOML {path.relative_to(ROOT).as_posix()}: {exc}')

    # Check links to files inside the package. HTTP source links are not fetched.
    local_links = 0
    for path in ROOT.rglob('*.md'):
        if is_ignored(path):
            continue
        body = path.read_text(encoding='utf-8')
        for target in re.findall(r'\[[^\]]*\]\(([^)\n]+)\)', body):
            if re.match(r'^(?:https?://|mailto:|#)', target):
                continue
            target = target.split('#')[0]
            if not target:
                continue
            local_links += 1
            check((path.parent / target).is_file(), f'Broken local link: {path.relative_to(ROOT)} -> {target}')

    backlog = read_json(ROOT / 'tasks/backlog.json') or {}
    tasks = backlog.get('tasks', [])
    ids = {task['id'] for task in tasks}
    check(len(ids) == len(tasks), 'Duplicate task IDs')
    check(len(tasks) == 14, 'Expected 14 execution tasks')
    done: set[str] = set()
    for task in tasks:
        check(task.get('status') == 'todo', f"Task incorrectly marked executed: {task['id']}")
        check(bool(task.get('acceptance')) and bool(task.get('outputs')), f"Incomplete task: {task['id']}")
        check(set(task.get('depends_on', [])) <= ids, f"Unknown dependency: {task['id']}")
    while True:
        newly = {t['id'] for t in tasks if t['id'] not in done and set(t['depends_on']) <= done}
        if not newly:
            break
        done |= newly
    check(done == ids, 'Cycle in task dependencies')

    with (ROOT / 'acceptance/test-matrix.csv').open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        check(reader.fieldnames == ['id', 'area', 'scenario', 'setup', 'expected', 'evidence', 'gate'], 'Wrong CSV columns')
        rows = list(reader)
    check(len({r['id'] for r in rows}) == len(rows), 'Duplicate test IDs')
    check(all(re.fullmatch(r'QA\d{3}', r['id']) for r in rows), 'Wrong test ID format')
    check(all(r['gate'] in {'G1', 'G2', 'G3'} for r in rows), 'Unknown test gate')
    check(all(r['evidence'].startswith('计划／未执行') for r in rows), 'A planned plugin test was incorrectly marked executed')

    event_counts = {}
    for path in (ROOT / 'fixtures/responses').glob('*.sse'):
        events = []
        for block in re.split(r'\r?\n\r?\n', path.read_text(encoding='utf-8')):
            if not block.strip():
                continue
            lines = block.splitlines()
            name = next((line[6:].strip() for line in lines if line.startswith('event:')), None)
            raw = '\n'.join(line[5:].lstrip() for line in lines if line.startswith('data:'))
            try:
                event = json.loads(raw)
            except ValueError:
                errors.append(f'Invalid synthetic SSE JSON: {path.name}')
                continue
            check(name == event.get('type'), f'SSE name/type mismatch: {path.name}')
            events.append(event)
        event_counts[path.name] = len(events)
        completed = any(e['type'] == 'response.completed' for e in events)
        check(completed == (path.name in {'text_completed.sse', 'refusal_completed.sse'}), f'Unexpected synthetic terminal: {path.name}')

    manifest = read_json(ROOT / 'TASKPACK_MANIFEST.json') or {}
    listed = {entry['path'] for entry in manifest.get('files', [])}
    actual = {
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob('*')
        if p.is_file() and p.name != 'TASKPACK_MANIFEST.json' and not is_ignored(p)
    }
    check(listed == actual, 'Manifest file set differs from package')
    for entry in manifest.get('files', []):
        path = ROOT / entry['path']
        if path.is_file():
            payload = path.read_bytes()
            check(len(payload) == entry['size_bytes'], f"Size mismatch: {entry['path']}")
            check(hashlib.sha256(payload).hexdigest() == entry['sha256'], f"SHA256 mismatch: {entry['path']}")

    result = {
        'taskpack_validation': 'pass' if not errors else 'fail',
        'plugin_test_execution': 'not_run',
        'planned_tasks': len(tasks), 'planned_tests': len(rows),
        'planned_tests_by_gate': dict(sorted(Counter(r['gate'] for r in rows).items())),
        'checked_local_links': local_links, 'synthetic_sse_events': event_counts,
        'file_count': len(actual) + 1, 'errors': errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
