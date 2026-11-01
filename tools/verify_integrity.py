#!/usr/bin/env python3
"""Verify a pinned Apple CNKL SHA-256 chunklist and trusted package signature.

Catalog Digest discrepancies are preserved. CNKL method 2 has an unkeyed
SHA-256 trailer; its authentication here comes from the pinned Apple HTTPS
download, not from treating that trailer as a certificate signature.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from apple_signature import trusted_apple_signature


def chunk_records(raw):
    if len(raw) < 36:
        raise ValueError('Truncated CNKL header')
    magic, header, version, method, signature, reserved, count, offset, trailer = struct.unpack_from('<4sI4BQQQ', raw)
    if (magic, header, version, method, signature, reserved) != (b'CNKL', 36, 1, 1, 2, 0):
        raise ValueError('Unsupported CNKL format; no signature method was silently skipped')
    if offset != header or not 1 <= count <= 1000000 or trailer != offset + count * 36 or len(raw) != trailer + 32:
        raise ValueError('Invalid CNKL bounds')
    if hashlib.sha256(raw[:trailer]).digest() != raw[trailer:]:
        raise ValueError('CNKL trailer SHA-256 mismatch')
    records = []
    for index in range(count):
        position = offset + index * 36
        size = struct.unpack_from('<I', raw, position)[0]
        if not 1 <= size <= 64 * 1024 ** 2:
            raise ValueError('Invalid chunk size')
        records.append((size, raw[position + 4:position + 36]))
    return records


def verify_file(package, raw, expected_size):
    records = chunk_records(raw)
    if sum(size for size, _ in records) != expected_size or package.stat().st_size != expected_size:
        raise ValueError('Package size does not match both catalog and chunklist')
    sha1, sha256 = hashlib.sha1(), hashlib.sha256()
    with package.open('rb') as stream:
        for index, (size, expected) in enumerate(records):
            block = stream.read(size)
            if hashlib.sha256(block).digest() != expected:
                raise ValueError('Apple chunk {} SHA-256 mismatch'.format(index))
            sha1.update(block)
            sha256.update(block)
    return {'actual_size': expected_size, 'sha1': sha1.hexdigest(), 'sha256': sha256.hexdigest(),
            'chunk_count': len(records), 'all_chunk_sha256_match': True,
            'chunklist_trailer_sha256_match': True, 'chunklist_sha256': hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--chunklist', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    raw = args.chunklist.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest.get('integrity_data_sha256'):
        parser.exit(2, 'Chunklist does not match the Apple HTTPS pin in the manifest\n')
    try:
        result = verify_file(args.package, raw, manifest['package']['Size'])
    except (OSError, ValueError, KeyError, struct.error) as error:
        parser.exit(2, 'ERROR: {}\n'.format(error))
    signature = subprocess.run(['pkgutil', '--check-signature', str(args.package)], capture_output=True, text=True)
    if not trusted_apple_signature(signature.returncode, signature.stdout):
        parser.exit(2, 'Trusted Apple package signature verification failed\n')
    manifest.update(result)
    manifest.update({
        'catalog_digest_match': result['sha1'] == manifest['package']['Digest'].lower(),
        'artifact_integrity_verified': True,
        'verification_method': 'APPLE_HTTPS_PINNED_CNKL_SHA256_AND_TRUSTED_APPLE_PACKAGE_SIGNATURE',
        'package_signature_exit': signature.returncode,
        'package_signature': (signature.stdout + signature.stderr).replace(str(args.package), args.package.name),
        'local_filename': args.package.name, 'runtime_verification': 'NOT_RUN',
        'chunklist_authentication': 'Apple HTTPS source pin; method-2 trailer is an unkeyed SHA-256 checksum',
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + '\n')
    if not manifest['catalog_digest_match']:
        print('WARN: catalog SHA-1 Digest differs; this discrepancy remains recorded.')
    print('PASS: {} Apple SHA-256 chunks and trusted Apple package signature'.format(result['chunk_count']))


if __name__ == '__main__':
    main()
