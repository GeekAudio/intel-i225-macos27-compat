#!/usr/bin/env python3
"""Extract a pinned full installer for offline inspection, without running its scripts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zlib
from offline_audit import sha256


def entries(package):
    with package.open('rb') as stream:
        header = stream.read(28)
        magic, header_size, version, compressed, uncompressed, _ = struct.unpack('>4sHHQQI', header)
        if magic != b'xar!' or version != 1 or not 28 <= header_size <= 4096 or compressed > 16 * 1024 ** 2 or uncompressed > 64 * 1024 ** 2:
            raise ValueError('Unsupported XAR header')
        stream.seek(header_size)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(stream.read(compressed), uncompressed + 1)
        if len(raw) != uncompressed or not decoder.eof:
            raise ValueError('XAR table size mismatch')
        toc = ET.fromstring(raw)
        result = {}
        for entry in toc.findall('./toc/file'):
            name = entry.findtext('name')
            if name not in ['Payload', 'SharedSupport.dmg']:
                continue
            encoding = entry.find('data/encoding')
            if encoding is None or encoding.get('style') != 'application/octet-stream':
                raise ValueError('Unexpected compression for ' + name)
            offset = header_size + compressed + int(entry.findtext('data/offset'))
            size = int(entry.findtext('data/length'))
            checksum = entry.find('data/archived-checksum')
            if checksum is None or checksum.get('style') != 'sha1':
                raise ValueError('Expected an archived SHA-1 for ' + name)
            if offset < header_size + compressed or size < 0 or offset + size > package.stat().st_size:
                raise ValueError('XAR member is outside the package')
            result[name] = {'offset': offset, 'size': size, 'sha1': checksum.text}
        if set(result) != {'Payload', 'SharedSupport.dmg'}:
            raise ValueError('Expected installer members were not found')
        return result


def extract(package, entry, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError('Extraction destination already exists: ' + destination.name)
    digest = hashlib.sha1()
    with package.open('rb') as source, destination.open('xb') as output:
        source.seek(entry['offset'])
        remaining = entry['size']
        while remaining:
            block = source.read(min(8 * 1024 ** 2, remaining))
            if not block:
                raise ValueError('Unexpected end of package')
            output.write(block)
            digest.update(block)
            remaining -= len(block)
    if digest.hexdigest() != entry['sha1']:
        raise ValueError('Extracted member checksum mismatch')
    return {'bytes': entry['size'], 'xar_sha1': digest.hexdigest(), 'sha256': sha256(destination)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if not manifest.get('catalog_digest_match') or sha256(args.package) != manifest.get('sha256'):
        parser.exit(2, 'Package does not match the verified download manifest\n')
    signature = subprocess.run(['pkgutil', '--check-signature', str(args.package)], capture_output=True, text=True)
    if signature.returncode or 'Apple Root CA' not in signature.stdout or 'Software Signing' not in signature.stdout:
        parser.exit(2, 'Apple package signature verification failed\n')
    if args.output.exists():
        parser.exit(2, 'Use a new output directory; existing data will not be overwritten\n')
    members = entries(args.package)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.output.parent).free < members['SharedSupport.dmg']['size'] + 2 * 1024 ** 3:
        parser.exit(2, 'Insufficient scratch space for extraction\n')
    args.output.mkdir(parents=True)
    payload = args.output / 'Payload'
    payload_record = extract(args.package, members['Payload'], payload)
    subprocess.run(['aa', 'extract', '-i', str(payload), '-d', str(args.output / 'expanded')], check=True)
    apps = list((args.output / 'expanded/Applications').glob('*.app'))
    if len(apps) != 1:
        parser.exit(2, 'Expected exactly one installer app in the package\n')
    shared = apps[0] / 'Contents/SharedSupport/SharedSupport.dmg'
    shared_record = extract(args.package, members['SharedSupport.dmg'], shared)
    result = {'package_sha256': manifest['sha256'], 'payload': payload_record,
              'shared_support': shared_record, 'app_relative_path': str(apps[0].relative_to(args.output)),
              'package_signature_exit': signature.returncode,
              'installer_scripts_executed': False, 'installer_launched': False}
    (args.output / 'prepared.json').write_text(json.dumps(result, indent=2) + '\n')
    (args.output / 'package-signature.txt').write_text(signature.stdout + signature.stderr)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
