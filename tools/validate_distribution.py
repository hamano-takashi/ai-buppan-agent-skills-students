#!/usr/bin/env python3
"""Offline checks for the exact learner distribution. Python standard library only."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

MANIFEST = 'distribution-manifest.json'
REQUIRED = {'README.md', 'AGENTS.md', 'CLAUDE.md', 'SKILLS_INDEX.md', 'SECURITY.md',
            'USAGE.md', 'THIRD_PARTY_NOTICES.md', '.gitignore', '.gitattributes',
            'tools/validate_distribution.py', 'tools/test_validate_distribution.py',
            'docs/START_HERE.md', 'docs/DISTRIBUTION.md', 'docs/RELEASE_REVIEW.md',
            'docs/IMAGES_2_5.md', 'docs/VERIFICATION.md', 'templates/project-context.md',
            'templates/image-brief.md', 'templates/worklog.md'}
ROOT_FILES = {name for name in REQUIRED if '/' not in name} | {MANIFEST}
SECRET_NAMES = re.compile(r'(^\.env(?:\.|$)|credentials|secret|^id_(rsa|ed25519)|^auth\.json$|\.(pem|key|p12|pfx)$)', re.I)
PATTERNS = {
    'personal-path': re.compile(r'(?<![\w/])/(?:Users|home)/[A-Za-z0-9_.-]+/|[A-Za-z]:[/\\]Users[/\\][A-Za-z0-9_.-]+[/\\]'),
    'api-key-shape': re.compile(r'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,}|AKIA[A-Z0-9]{16})\b'),
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'private-service-url': re.compile(r'https?://(?:[^/\s]*\.)?(?:notion\.so|notion\.site|docs\.google\.com|drive\.google\.com|slack\.com|chatwork\.com)/[^\s`<>]+'),
    'shell-download-execute': re.compile(r'^\s*(?:curl|wget)\b[^\n]*\|\s*(?:sh|bash)\b', re.M),
    'destructive-delete-recipe': re.compile(r'^\s*(?:sudo\s+)?rm\s+-[rf]*r[rf]*f[rf]*\s+', re.M),
}


def permitted(rel: str) -> bool:
    p = Path(rel)
    if len(p.parts) == 1:
        return rel in ROOT_FILES
    if p.parts[0] in {'docs', 'templates'}:
        return rel in REQUIRED
    if p.parts[0] == 'tools':
        return rel in REQUIRED
    if p.parts[:2] == ('.agents', 'skills'):
        return len(p.parts) >= 4 and p.suffix == '.md'
    return False


def inventory(root: Path) -> tuple[list[Path], list[str]]:
    files, errors = [], []
    def visit(directory: Path) -> None:
        for p in sorted(directory.iterdir()):
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                errors.append(f'{rel}: symlink is not distributable')
                continue
            if p.name == '.git' and p.parent == root:
                continue
            if p.is_dir():
                if SECRET_NAMES.search(p.name):
                    errors.append(f'{rel}: forbidden sensitive directory (not traversed)')
                    continue
                if p.name == '__pycache__':
                    continue
                visit(p)
            elif p.is_file():
                # Refuse names before reading contents.
                if SECRET_NAMES.search(p.name):
                    errors.append(f'{rel}: forbidden sensitive filename (not read)')
                elif not permitted(rel):
                    errors.append(f'{rel}: not in permitted distribution layout (not read)')
                else:
                    files.append(p)
            else:
                errors.append(f'{rel}: non-regular file')
    visit(root)
    return files, errors


def markdown_links(root: Path, p: Path, text: str) -> list[str]:
    errors = []
    # Fenced illustrative examples aren't references supplied by this package.
    text = re.sub(r'(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$', '', text)
    for raw in re.findall(r'!?\[[^\]\n]*\]\(([^\)\n]+)\)', text):
        value = raw.strip().split(' "', 1)[0].strip('<>')
        parsed = urlsplit(value)
        if parsed.scheme in {'http', 'https', 'mailto'} or value.startswith('#'):
            continue
        if parsed.scheme or value.startswith('//'):
            errors.append(f'{p.relative_to(root)}: unsupported link scheme')
            continue
        target = unquote(parsed.path)
        if not target:
            continue
        dest = root / target if target.startswith('.agents/') else p.parent / target
        dest = dest.resolve()
        if not dest.is_relative_to(root.resolve()):
            errors.append(f'{p.relative_to(root)}: link outside distribution')
        elif not dest.exists():
            errors.append(f'{p.relative_to(root)}: missing link: {target}')
    return errors


def validate(root: Path, check_manifest: bool = True) -> tuple[list[str], dict[str, str]]:
    files, errors = inventory(root)
    rels = {p.relative_to(root).as_posix() for p in files}
    errors.extend(f'{p}: required file missing' for p in sorted(REQUIRED - rels))
    hashes, skill_names = {}, set()
    index = (root / 'SKILLS_INDEX.md').read_text(encoding='utf-8') if 'SKILLS_INDEX.md' in rels else ''
    for p in files:
        rel = p.relative_to(root).as_posix()
        data = p.read_bytes()
        if len(data) > 1_000_000 or b'\x00' in data:
            errors.append(f'{rel}: oversized or binary file')
            continue
        try:
            text = data.decode('utf-8')
            if any(ord(c) < 32 and c not in '\t\n\r' for c in text):
                errors.append(f'{rel}: non-text control characters')
                continue
        except UnicodeDecodeError:
            errors.append(f'{rel}: not UTF-8')
            continue
        if rel != MANIFEST:
            hashes[rel] = hashlib.sha256(data).hexdigest()
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                errors.append(f'{rel}: {label} detected (value not printed)')
        if p.suffix == '.md':
            errors.extend(markdown_links(root, p, text))
        if p.name == 'SKILL.md':
            m = re.match(r'\A---\nname: ([a-z0-9-]{1,64})\ndescription: ("[^\n]*")\n---\n', text)
            if not m:
                errors.append(f'{rel}: invalid supported frontmatter')
                continue
            try:
                description = json.loads(m[2])
            except json.JSONDecodeError:
                errors.append(f'{rel}: description is not a valid quoted string')
                continue
            if not isinstance(description, str) or not description.strip() or len(description) > 1024:
                errors.append(f'{rel}: invalid description')
            name = m[1]
            if name != p.parent.name or name in skill_names:
                errors.append(f'{rel}: skill name mismatch or duplicate')
            skill_names.add(name)
            if f']({rel})' not in index:
                errors.append(f'{rel}: not linked from skill index')
    if not skill_names:
        errors.append('No skills found')
    if check_manifest:
        p = root / MANIFEST
        if not p.is_file() or p.is_symlink():
            errors.append('Distribution manifest missing')
        else:
            try:
                manifest = json.loads(p.read_text(encoding='utf-8'))
                if manifest.get('schema_version') != 1 or manifest.get('files') != hashes:
                    errors.append('Distribution manifest does not match current files')
                if manifest.get('skill_count') != len(skill_names):
                    errors.append('Distribution manifest skill count mismatch')
            except (ValueError, TypeError, AttributeError):
                errors.append('Distribution manifest invalid')
    return errors, hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--write-manifest', action='store_true', help='Maintainer only: after content review, record current file hashes')
    args = parser.parse_args()
    root = args.root.resolve()
    errors, hashes = validate(root, check_manifest=not args.write_manifest)
    if errors:
        for err in sorted(set(errors)):
            print(f'FAIL {err}')
        return 1
    count = sum(p.endswith('/SKILL.md') for p in hashes)
    if args.write_manifest:
        payload = {'schema_version': 1, 'release': '1.1.0', 'skill_count': count, 'files': hashes}
        (root / MANIFEST).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print('Recorded manifest. This does not replace confidentiality or rights review.')
    print(f'PASS {len(hashes)} files; {count} skills; structure, patterns, metadata and local links checked.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
