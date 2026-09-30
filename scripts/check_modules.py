#!/usr/bin/env python3
"""Run module checks once a module has a build manifest."""
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd):
    subprocess.run(args, cwd=cwd, check=True)


def require_manifest(module, manifest, suffixes):
    if not (module / manifest).exists() and any(p.suffix in suffixes for p in module.rglob("*") if p.is_file() and not any(x in p.parts for x in ["node_modules", ".venv", "target", "dist", "__pycache__"])):
        raise RuntimeError(f"{module.name}: source exists but {manifest} is missing")


def main():
    java = ROOT / 'java-environment'
    require_manifest(java, 'pom.xml', {'.java'})
    if (java / 'pom.xml').exists():
        if not (java / 'mvnw').exists():
            raise RuntimeError('Java module requires Maven Wrapper')
        run(['./mvnw', '-B', 'verify'], java)
    else:
        print('SKIP Java: no implementation manifest')
    for name in ['agent-runtime', 'evo-harness', 'benchmark']:
        module = ROOT / name
        require_manifest(module, "pyproject.toml", {".py"})
        if (module / 'pyproject.toml').exists():
            run([sys.executable, '-m', 'pip', 'install', '-e', '.[test]'], module)
            run([sys.executable, '-m', 'ruff', 'format', '--check', '.'], module)
            run([sys.executable, '-m', 'ruff', 'check', '.'], module)
            run([sys.executable, '-m', 'pytest', '-q'], module)
        else:
            print(f'SKIP {name}: no implementation manifest')
    web = ROOT / 'web'
    require_manifest(web, 'package.json', {'.vue', '.ts', '.tsx', '.js', '.jsx'})
    if (web / 'package.json').exists():
        if not (web / 'package-lock.json').exists():
            raise RuntimeError('Web module requires package-lock.json for npm ci')
        run(['npm', 'ci'], web)
        for name in ['lint', 'typecheck', 'test:unit', 'build']:
            run(['npm', 'run', name], web)
    else:
        print('SKIP Web: no implementation manifest')


if __name__ == '__main__':
    main()
