#!/usr/bin/env python3
"""Basic repository disclosure/link checks; not a complete security audit."""
import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|sk-(?:proj-)?[A-Za-z0-9_-]{35,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
PRIVATE_EXTENSIONS = {'.xls', '.xlsx', '.pdf', '.log'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--staged', action='store_true')
    args = parser.parse_args()
    if args.staged:
        listing = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'], cwd=ROOT)
        paths = [ROOT / name.decode() for name in listing.split(b'\0') if name]
    else:
        ignored = {'.git', '.venv', 'node_modules', 'target', 'dist', '__pycache__'}
        paths = [p for p in ROOT.rglob('*') if p.is_file() and not (set(p.relative_to(ROOT).parts) & ignored) and not p.is_relative_to(ROOT / 'data')]
    errors = []
    for path in paths:
        rel = path.relative_to(ROOT)
        if rel.parts[:2] in [('data', 'raw'), ('data', 'private')] or path.suffix in PRIVATE_EXTENSIONS or (path.name.startswith('.env') and path.name != '.env.example'):
            errors.append(f'{rel}: private input/log file must not be committed')
            continue
        raw = subprocess.check_output(['git', 'show', ':' + rel.as_posix()], cwd=ROOT) if args.staged else path.read_bytes()
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            continue
        if SECRET.search(text):
            errors.append(f'{rel}: possible credential/private key')
        if path.suffix == '.md':
            for dest in re.findall(r'\]\(([^)\n]+)\)', text):
                dest = dest.strip('<>').split('#', 1)[0]
                if not dest or '://' in dest or dest.startswith('mailto:'):
                    continue
                if dest.startswith('/Users/'):
                    errors.append(f'{rel}: public docs should use repository-relative links')
                elif not (path.parent / dest).exists():
                    errors.append(f'{rel}: missing local link {dest}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(paths)} files; basic disclosure and local Markdown link checks')
    print('Scope: text checks only; no guarantee against all secrets or runtime vulnerabilities')


if __name__ == '__main__':
    main()
