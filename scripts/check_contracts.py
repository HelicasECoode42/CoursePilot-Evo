#!/usr/bin/env python3
"""Validate local contracts without reaching external schema URLs."""
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / 'contracts'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def walk_refs(value):
    if isinstance(value, dict):
        if '$ref' in value:
            yield value['$ref']
        for child in value.values():
            yield from walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_refs(child)


def check_ref(base, ref):
    url, _, fragment = ref.partition('#')
    if urlparse(url).scheme not in ('', 'file'):
        raise ValueError(f'{base.name}: external schema lookup forbidden: {ref}')
    target = Path(unquote(urlparse(url).path)) if url.startswith('file:') else base.parent / url
    target = target.resolve() if url else base
    if not target.is_relative_to(ROOT):
        raise ValueError('Schema reference escapes repository')
    node = load(target)
    if fragment:
        if not fragment.startswith('/'):
            raise ValueError(f'Unsupported anchor: {fragment}')
        for part in fragment[1:].split('/'):
            node = node[part.replace('~1', '/').replace('~0', '~')]


def main():
    files = list(CONTRACTS.glob('*.openapi.json')) + list((CONTRACTS / 'schemas').glob('*.json'))
    for path in files:
        doc = load(path)
        for ref in walk_refs(doc):
            check_ref(path, ref)
        if path.name.endswith('.openapi.json'):
            validate(doc, base_uri=path.as_uri())
        else:
            Draft202012Validator.check_schema(doc)
    schema_path = CONTRACTS / 'schemas/domain.schema.json'
    registry = Registry().with_resource(schema_path.as_uri(), Resource.from_contents(load(schema_path)))
    entries = load(CONTRACTS / 'examples/index.json')
    for entry in entries:
        instance = load(CONTRACTS / 'examples' / entry['file'])
        validator = Draft202012Validator(
            {'$ref': schema_path.as_uri() + '#/$defs/' + entry['definition']},
            registry=registry, format_checker=FormatChecker(),
        )
        errors = list(validator.iter_errors(instance))
        if bool(errors) == entry['valid']:
            detail = '; '.join(error.message for error in errors)
            raise AssertionError(f"Unexpected result: {entry['file']}: {detail}")
    print(f'PASS: {len(files)} schema/OpenAPI documents; local refs; {len(entries)} positive/negative examples')


if __name__ == '__main__':
    main()
