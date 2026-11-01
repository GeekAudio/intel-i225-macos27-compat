#!/usr/bin/env python3
"""Inspect actual kernel entries in the installer's mounted MobileAsset ZIP."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import re
import zipfile
from offline_audit import macho_architectures
from unpack_kernel import payload, decode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--target-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--keep-kernel', default='kernelcache.release.mac14j')
    parser.add_argument('--keep-directory', type=Path, required=True)
    args = parser.parse_args()
    target = json.loads(args.target_manifest.read_text())
    records = []
    with zipfile.ZipFile(args.archive) as archive:
        version = plistlib.loads(archive.read('AssetData/boot/SystemVersion.plist'))
        if (version.get('ProductVersion'), version.get('ProductBuildVersion')) != (target['version'], target['build']):
            parser.exit(2, 'Archive SystemVersion.plist does not match the pinned target\n')
        kernels = [entry for entry in archive.infolist()
                   if not entry.is_dir() and PurePosixPath(entry.filename).name.lower().startswith('kernelcache.')]
        if not kernels:
            parser.exit(2, 'No kernel entries were found; architecture is unresolved\n')
        for entry in sorted(kernels, key=lambda entry: entry.filename):
            record = {'entry': entry.filename, 'zip_uncompressed_bytes': entry.file_size}
            try:
                if entry.file_size > 512 * 1024 ** 2:
                    raise ValueError('Entry exceeds the inspection memory bound')
                wrapped = archive.read(entry)  # ZipFile also checks the member CRC.
                body, container = payload(wrapped)
                decoded, compression = decode(body)
                architectures = macho_architectures(decoded)
                if not architectures:
                    raise ValueError('Decoded header has no recognized architecture')
                match = re.search(rb'Darwin Kernel Version [^\x00\n]{1,400}', decoded)
                record.update({'status': 'HEADER_RECOGNIZED', 'container': container, 'compression': compression,
                               'wrapped_sha256': hashlib.sha256(wrapped).hexdigest(),
                               'decoded_sha256': hashlib.sha256(decoded).hexdigest(),
                               'decoded_bytes': len(decoded), 'architectures': architectures,
                               'darwin_version_string': match.group().decode('ascii', errors='replace') if match else None})
                if PurePosixPath(entry.filename).name == args.keep_kernel:
                    args.keep_directory.mkdir(parents=True, exist_ok=True)
                    (args.keep_directory / (args.keep_kernel + '.im4p')).write_bytes(wrapped)
                    (args.keep_directory / (args.keep_kernel + '.kc')).write_bytes(decoded)
            except (OSError, ValueError, zipfile.BadZipFile) as error:
                record.update(status='UNRESOLVED', error=str(error))
            records.append(record)
            print(PurePosixPath(entry.filename).name, record['status'], record.get('architectures', []), flush=True)
    unresolved = any(record['status'] != 'HEADER_RECOGNIZED' for record in records)
    contains_x86 = any('x86_64' in record.get('architectures', []) for record in records)
    result = {'scope': 'Kernel entries in this specific shipped MobileAsset archive, not a boot test',
              'version': target['version'], 'build': target['build'], 'parent_package_sha256': target['sha256'],
              'archive_filename': args.archive.name, 'archive_bytes': args.archive.stat().st_size,
              'kernel_count': len(records), 'kernel_records': records,
              'status': 'UNRESOLVED_KERNEL_ENTRIES' if unresolved else (
                  'X86_64_ENTRY_PRESENT_ABI_UNVERIFIED' if contains_x86 else 'NO_X86_64_IN_SHIPPED_KERNEL_ENTRIES'),
              'runtime_verification': 'NOT_RUN'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], flush=True)
    return 1 if unresolved else 0


if __name__ == '__main__':
    raise SystemExit(main())
