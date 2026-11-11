#!/usr/bin/env python3
"""Prepare the tested Golden Gate I210 kext in a local staging directory."""

import argparse
from pathlib import Path
import plistlib
import shutil
from tempfile import TemporaryDirectory

from offline_audit import read_plist, sha256


BUNDLE_NAME = 'AppleIntelI210Ethernet-27.kext'
INFO_PATH = Path('Contents/Info.plist')
BINARY_PATH = Path('Contents/MacOS/AppleIntelI210Ethernet')
BINARY_SHA256 = 'c2639077ffe5f491e5624782bd59fbc916730fb0c4515b2b5cee004073a40841'
SOURCE_INFO_SHA256 = '71aade8f8316c0a07b8c4a737fa99c043727cdc251bdeeeafba50cbd17b42c66'
AVB_BUNDLE = 'com.apple.iokit.IOEthernetAVBController'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kext', required=True, type=Path, help='AppleIntelI210Ethernet.kext from the Tahoe baseline')
    parser.add_argument('--output-dir', required=True, type=Path, help='existing local directory for the output bundle')
    args = parser.parse_args()

    target = args.output_dir / BUNDLE_NAME
    try:
        if sha256(args.kext / BINARY_PATH) != BINARY_SHA256:
            raise ValueError('I210 executable does not match the tested 2.3.1 build')
        if sha256(args.kext / INFO_PATH) != SOURCE_INFO_SHA256:
            raise ValueError('I210 Info.plist does not match the unmodified Tahoe baseline')

        info = read_plist(args.kext / INFO_PATH)
        del info['OSBundleLibraries'][AVB_BUNDLE]
        prepared_info = plistlib.dumps(info, sort_keys=False)

        if target.exists() or target.is_symlink():
            raise FileExistsError(f'Output already exists: {target}')
        with TemporaryDirectory(dir=args.output_dir) as directory:
            staged = Path(directory) / BUNDLE_NAME
            shutil.copytree(args.kext, staged)
            (staged / INFO_PATH).write_bytes(prepared_info)
            staged.rename(target)
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(target)


if __name__ == '__main__':
    main()
