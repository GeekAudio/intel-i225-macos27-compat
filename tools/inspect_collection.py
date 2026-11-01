#!/usr/bin/env python3
"""Inspect one explicit offline collection; do not mix in host collections."""
import argparse
import json
from pathlib import Path
import plistlib
import re
import subprocess
from offline_audit import bundle_version, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection', type=Path, required=True)
    parser.add_argument('--candidate-report', type=Path, required=True)
    parser.add_argument('--arch', choices=['x86_64', 'arm64', 'arm64e'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    candidate = json.loads(args.candidate_report.read_text())
    required = set(candidate['undefined_symbols'][args.arch])
    missing_system = args.collection.parent / '__not_supplied_system.kc'
    missing_aux = args.collection.parent / '__not_supplied_aux.kc'
    if missing_system.exists() or missing_aux.exists():
        parser.exit(2, 'Reserved absent-collection paths already exist\n')
    command = ['kmutil', 'inspect', '-B', str(args.collection), '-S', str(missing_system),
               '-A', str(missing_aux), '-M', '--no-variant-extension', '--arch', args.arch, '--show-prelink-info']
    prelink = subprocess.run(command, capture_output=True, text=True)
    names = subprocess.run(['nm', '-arch', args.arch, '-gU', str(args.collection)], capture_output=True, text=True)
    if prelink.returncode or names.returncode:
        parser.exit(2, 'The target collection could not be inspected; no host fallback was used\n')
    text = prelink.stdout
    if text.count('kernel collection at ') != 1:
        parser.exit(2, 'Expected exactly one collection in the inspection result\n')
    start, end = text.find('<?xml'), text.find('</plist>')
    if start < 0 or end < start:
        parser.exit(2, 'The target prelink plist could not be extracted\n')
    entries = plistlib.loads(text[start:end + len('</plist>')].encode())['_PrelinkInfoDictionary']
    inventory = {entry.get('CFBundleIdentifier'): entry for entry in entries}
    rows = []
    for identifier, minimum in candidate['bundle_libraries'].items():
        provider = inventory.get(identifier)
        version = str(provider.get('CFBundleVersion')) if provider else None
        parsed, needed = bundle_version(version) if version else None, bundle_version(minimum)
        rows.append({'identifier': identifier, 'candidate_minimum': minimum,
                     'target_collection_version': version,
                     'status': 'PRESENT_IN_THIS_COLLECTION' if provider else 'NOT_LISTED_IN_THIS_COLLECTION',
                     'version_minimum_satisfied': parsed >= needed if parsed is not None and needed is not None else None})
    exports = set(re.findall(r'^[0-9a-fA-F]+\s+\S\s+(\S+)\s*$', names.stdout, re.M))
    absent = sorted(required - exports)
    result = {'scope': 'This collection only; defined names are not linker authorization or C++ ABI proof',
              'collection_filename': args.collection.name, 'collection_sha256': sha256(args.collection),
              'collection_bundle_count': len(entries), 'candidate_architecture': args.arch,
              'candidate_binary_sha256': candidate['binary_sha256'],
              'host_collections_used': False, 'host_symbol_sources_used': False,
              'dependencies': rows, 'candidate_import_count': len(required),
              'target_defined_global_name_count': len(exports), 'present_name_count': len(required & exports),
              'missing_names': absent, 'missing_name_count': len(absent),
              'status': 'STATIC_INCOMPLETE' if absent or any(row['version_minimum_satisfied'] is not True for row in rows)
                        else 'STATIC_NAMES_AND_VERSIONS_ONLY',
              'runtime_verification': 'NOT_RUN', 'abi_verification': 'NOT_ESTABLISHED',
              'limits': ['Missing entries may be supplied elsewhere in the full target OS.',
                         'Do not remove dependencies or create placeholder symbols merely to satisfy this scan.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], 'missing names:', len(absent), flush=True)
    return 1 if result['status'] == 'STATIC_INCOMPLETE' else 0


if __name__ == '__main__':
    raise SystemExit(main())
