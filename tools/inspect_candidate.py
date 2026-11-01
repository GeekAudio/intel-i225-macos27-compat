#!/usr/bin/env python3
"""Record a local candidate's identities, architectures, dependencies and imports."""
import argparse
import json
from pathlib import Path
import subprocess
from offline_audit import macho_architectures, read_plist, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kext', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    info_path = args.kext / 'Contents/Info.plist'
    info = read_plist(info_path)
    executable = info['CFBundleExecutable']
    if Path(executable).name != executable:
        parser.error('Invalid executable name')
    binary = args.kext / 'Contents/MacOS' / executable
    architectures = macho_architectures(binary)
    imports = {}
    for arch in architectures:
        result = subprocess.run(['nm', '-arch', arch, '-u', str(binary)], capture_output=True, text=True)
        if result.returncode:
            parser.exit(2, 'nm could not inspect a candidate slice\n')
        imports[arch] = sorted(set(line.strip() for line in result.stdout.splitlines()
                                   if line.strip().startswith('_')))
    data = {'bundle_identifier': info.get('CFBundleIdentifier'), 'version': info.get('CFBundleVersion'),
            'binary_sha256': sha256(binary), 'info_plist_sha256': sha256(info_path),
            'architectures': architectures, 'build_sdk': info.get('DTSDKName'),
            'minimum_system_version': info.get('LSMinimumSystemVersion'),
            'bundle_libraries': info.get('OSBundleLibraries'),
            'personalities': {key: {k: value[k] for k in ['IOClass', 'IOPCIPrimaryMatch', 'IONameMatch'] if k in value}
                              for key, value in info.get('IOKitPersonalities', {}).items()},
            'undefined_symbol_count': {arch: len(symbols) for arch, symbols in imports.items()},
            'undefined_symbols': imports, 'runtime_verification': 'NOT_RUN'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({k: data[k] for k in ['version', 'binary_sha256', 'architectures', 'undefined_symbol_count']}, indent=2))


if __name__ == '__main__':
    main()
