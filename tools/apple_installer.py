#!/usr/bin/env python3
"""Discover and download Apple's public macOS 27 full installer; never install it."""
import argparse
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

CATALOG = ('https://swscan.apple.com/content/catalogs/others/'
           'index-27-26-15-14-13-12-10.16-10.15-10.14-10.13-10.12-10.11-'
           '10.10-10.9-mountainlion-lion-snowleopard-leopard.merged-1.sucatalog.gz')
PUBLIC_VERSIONS = 'https://gdmf.apple.com/v2/pmv'


def apple_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or not (p.hostname or '').endswith('.apple.com') or p.username or p.password:
        raise ValueError('Only credential-free Apple HTTPS URLs are accepted')
    return url


def get(url):
    with urllib.request.urlopen(apple_url(url), timeout=60) as response:
        apple_url(response.url)
        return response.read()


def discover(output):
    public_assets = json.loads(get(PUBLIC_VERSIONS))['PublicAssetSets']['macOS']
    released = {(asset['ProductVersion'], asset['Build']) for asset in public_assets}
    raw = get(CATALOG)
    catalog = plistlib.loads(gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw)
    candidates = []
    for product_id, product in catalog.get('Products', {}).items():
        identifiers = product.get('ExtendedMetaInfo', {}).get('InstallAssistantPackageIdentifiers', {})
        if 'GoldenGate' not in ' '.join(identifiers.values()):
            continue
        distribution_url = product.get('Distributions', {}).get('English')
        if not distribution_url:
            continue
        distribution = get(distribution_url)
        tree = ET.fromstring(distribution)
        aux = tree.find('./auxinfo/dict')
        if aux is None:
            continue
        children = list(aux)
        values = {children[i].text: children[i + 1].text for i in range(0, len(children) - 1, 2)}
        version, build = values.get('VERSION', ''), values.get('BUILD', '')
        if not re.fullmatch(r'27(?:\.\d+)*', version) or (version, build) not in released:
            continue
        package = next((p for p in product.get('Packages', [])
                        if p.get('URL', '').endswith('/InstallAssistant.pkg')), None)
        if package:
            candidates.append((tuple(map(int, version.split('.'))), str(product.get('PostDate')), {
                'product_id': product_id, 'version': version, 'build': build,
                'catalog_url': CATALOG, 'distribution_url': distribution_url,
                'public_versions_url': PUBLIC_VERSIONS, 'public_release_confirmed': True,
                'distribution_sha256': hashlib.sha256(distribution).hexdigest(),
                'package': package,
                'discovered_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }, distribution))
    if not candidates:
        raise ValueError('No public macOS 27 full installer was found; no older OS was substituted')
    _, _, manifest, distribution = max(candidates, key=lambda c: (c[0], c[1]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + '\n')
    output.with_suffix('.dist').write_bytes(distribution)
    print(json.dumps(manifest, indent=2))


def download(manifest_path, destination):
    manifest = json.loads(manifest_path.read_text())
    if not re.fullmatch(r'27(?:\.\d+)*', manifest.get('version', '')):
        raise ValueError('The pinned manifest does not identify macOS 27')
    package = manifest['package']
    url, size = apple_url(package['URL']), int(package['Size'])
    digest = package.get('Digest', '').lower()
    if not re.fullmatch(r'[0-9a-f]{40}', digest):
        raise ValueError('A catalog SHA-1 digest is required before downloading')
    destination.mkdir(parents=True, exist_ok=True)
    filename = 'InstallAssistant-{}-{}.pkg'.format(manifest['version'], manifest['build'])
    final, partial = destination / filename, destination / (filename + '.partial')
    path = final if final.exists() else partial
    offset = path.stat().st_size if path.exists() else 0
    if offset > size:
        raise ValueError('Existing file is larger than the pinned package')
    if not final.exists() and offset < size:
        if shutil.disk_usage(destination).free < size - offset + 2 * 1024 ** 3:
            raise ValueError('Insufficient free space for the download plus 2 GiB reserve')
        request = urllib.request.Request(url, headers={'Range': 'bytes={}-'.format(offset)} if offset else {})
        with urllib.request.urlopen(request, timeout=90) as response:
            apple_url(response.url)
            if offset and (response.status != 206 or not response.headers.get('Content-Range', '').startswith('bytes {}-'.format(offset))):
                raise ValueError('Server did not honor resume; partial file was preserved')
            with partial.open('ab' if offset else 'wb') as stream:
                while True:
                    block = response.read(8 * 1024 * 1024)
                    if not block:
                        break
                    if offset + len(block) > size:
                        raise ValueError('Response exceeds the catalog package size')
                    stream.write(block)
                    offset += len(block)
                    print('{:.1f}%'.format(offset * 100 / size), flush=True)
                stream.flush()
                os.fsync(stream.fileno())
    if path.stat().st_size != size:
        raise ValueError('Downloaded size differs from the catalog')
    sha1, sha256 = hashlib.sha1(), hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            sha1.update(block)
            sha256.update(block)
    if sha1.hexdigest() != digest:
        raise ValueError('Catalog SHA-1 mismatch; file was not promoted to a verified package')
    if path == partial:
        partial.rename(final)
    manifest.update(local_filename=filename, actual_size=size, sha1=sha1.hexdigest(),
                    sha256=sha256.hexdigest(), catalog_digest_match=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ['version', 'build', 'sha256', 'catalog_digest_match']}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    discover_parser = sub.add_parser('discover')
    discover_parser.add_argument('--output', type=Path, required=True)
    download_parser = sub.add_parser('download')
    download_parser.add_argument('--manifest', type=Path, required=True)
    download_parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'discover':
            discover(args.output)
        else:
            download(args.manifest, args.destination)
    except (OSError, ValueError, KeyError, ET.ParseError, plistlib.InvalidFileException) as error:
        parser.exit(2, 'ERROR: {}\n'.format(error))


if __name__ == '__main__':
    main()
