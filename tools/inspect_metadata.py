#!/usr/bin/env python3
"""Summarize downloaded Apple distribution and MobileAsset metadata without executing it."""
import argparse
import base64
import hashlib
import json
import lzma
from pathlib import Path
import plistlib
import re
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distribution', type=Path, required=True)
    parser.add_argument('--mobile-asset-plist', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--build', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw_dist = args.distribution.read_bytes()
    raw_assets = args.mobile_asset_plist.read_bytes()
    aux = ET.fromstring(raw_dist).find('./auxinfo/dict')
    children = list(aux) if aux is not None else []
    distribution_values = {children[i].text: children[i + 1].text for i in range(0, len(children) - 1, 2)}
    if (distribution_values.get('VERSION'), distribution_values.get('BUILD')) != (args.version, args.build):
        parser.exit(2, 'Distribution does not match the pinned target\n')
    assets = plistlib.loads(raw_assets)['Assets']
    pairs = sorted(set((a.get('OSVersion'), a.get('Build')) for a in assets))
    if pairs != [(args.version, args.build)]:
        parser.exit(2, 'MobileAsset metadata does not match the pinned target\n')
    identities = []
    for asset in assets:
        manifest = plistlib.loads(lzma.decompress(base64.b64decode(asset['PreflightBuildManifest'])))
        if (manifest.get('ProductVersion'), manifest.get('ProductBuildVersion')) != (args.version, args.build):
            parser.exit(2, 'Embedded build manifest does not match the pinned target\n')
        for identity in manifest['BuildIdentities']:
            identities.append({
                'device_class': identity.get('Info', {}).get('DeviceClass'),
                'variant': identity.get('Info', {}).get('Variant'),
                'kernel_path': identity.get('Manifest', {}).get('KernelCache', {}).get('Info', {}).get('Path'),
                'platform': identity.get('Ap,SDKPlatform'),
            })
    boards = re.search(r'var supportedBoardIDs\s*=\s*(\[[^;]*\]);', raw_dist.decode())
    result = {
        'target_version': args.version, 'target_build': args.build,
        'distribution_sha256': hashlib.sha256(raw_dist).hexdigest(),
        'mobile_asset_plist_sha256': hashlib.sha256(raw_assets).hexdigest(),
        'asset_count': len(assets), 'asset_versions_builds': pairs,
        'distribution_supported_board_ids_expression': boards.group(1) if boards else None,
        'supported_device_models': sorted(set(d for a in assets for d in a.get('SupportedDeviceModels', []))),
        'cryptex_tags': sorted(set(c['CryptexTag'] for a in assets for c in a.get('CryptexSizeInfo', []))),
        'build_identities': identities,
        'limits': ['Metadata inventories describe shipped assets; they do not prove kernel headers or driver ABI compatibility.',
                   'IsUniversal is not treated as evidence of an Intel kernel.'],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('Assets: {}; build identities: {}'.format(len(assets), len(identities)))


if __name__ == '__main__':
    main()
