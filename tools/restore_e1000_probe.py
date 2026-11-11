#!/usr/bin/env python3
"""Restore e1000=0 handling in the tested 26B123 EEE-off E1000 executable."""

import argparse
from hashlib import sha256
import os
from pathlib import Path


INPUT_SHA256 = 'ed2f60274dc16a8078532e22ff06df7285e55c1e4269014248a3e4ad6190d9ee'
OUTPUT_SHA256 = '62e312646fe8d59682be94fb3bbf9a8019ac421db5c9718205efc2d9bbc02c38'
PROBE_OFFSET = 0x1CED6
CODE_PAGE = slice(0x1C000, 0x1D000)
CODE_DIRECTORY_HASH = slice(0x72313, 0x72333)


def restore_probe(executable):
    if sha256(executable).hexdigest() != INPUT_SHA256:
        raise ValueError('expected the tested x86_64 26B123 EEE-off E1000 executable')

    patched = bytearray(executable)
    # Restore the stock jump on e1000=0 and refresh the changed ad-hoc code page hash.
    patched[PROBE_OFFSET:PROBE_OFFSET + 6] = bytes.fromhex('0f848f000000')
    patched[CODE_DIRECTORY_HASH] = sha256(patched[CODE_PAGE]).digest()
    if sha256(patched).hexdigest() != OUTPUT_SHA256:
        raise ValueError('restored executable does not match the tested output')
    return patched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path, help='local copy of the E1000 executable')
    parser.add_argument('--output', required=True, type=Path, help='new path for the restored executable')
    args = parser.parse_args()

    try:
        restored = restore_probe(args.input.read_bytes())
        with args.output.open('xb') as output:
            output.write(restored)
            os.fchmod(output.fileno(), 0o755)
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(f'{OUTPUT_SHA256}  {args.output}')


if __name__ == '__main__':
    main()
