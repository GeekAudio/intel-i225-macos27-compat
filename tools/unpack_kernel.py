#!/usr/bin/env python3
"""Unwrap a local IM4P kernelcache and decode LZFSE with macOS libcompression."""
import argparse
import ctypes
import json
from pathlib import Path
from offline_audit import macho_architectures, sha256


def der_items(data, start=0, end=None):
    end = len(data) if end is None else end
    while start < end:
        if start + 2 > end:
            raise ValueError('Truncated DER header')
        tag, length = data[start], data[start + 1]
        position = start + 2
        if length & 128:
            count = length & 127
            if not 1 <= count <= 8 or position + count > end:
                raise ValueError('Unsupported DER length')
            length = int.from_bytes(data[position:position + count], 'big')
            position += count
        stop = position + length
        if stop > end:
            raise ValueError('DER value exceeds container')
        yield tag, position, stop
        start = stop


def payload(data):
    if data[:4] in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf'):
        return data, 'Mach-O'
    def search(start, stop, depth):
        if depth > 8:
            return None
        fields = list(der_items(data, start, stop))
        if fields and data[fields[0][1]:fields[0][2]] == b'IM4P':
            if len(fields) < 4 or fields[3][0] != 4:
                raise ValueError('IM4P payload was not found')
            return data[fields[3][1]:fields[3][2]]
        for tag, a, b in fields:
            if tag & 32:
                found = search(a, b, depth + 1)
                if found is not None:
                    return found
        return None
    result = search(0, len(data), 0)
    if result is None:
        raise ValueError('No IM4P structure was found')
    return result, 'IM4P'


def decode(data):
    if data[:4] in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf'):
        return data, 'none'
    if data[:4] not in (b'bvx2', b'bvxn', b'bvx-', b'bvx1'):
        raise ValueError('Unsupported compression; input retained for another decoder')
    lib = ctypes.CDLL('/usr/lib/libcompression.dylib')
    function = lib.compression_decode_buffer
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                         ctypes.c_void_p, ctypes.c_int]
    function.restype = ctypes.c_size_t
    source = ctypes.create_string_buffer(data)
    for megabytes in [32, 64, 128, 256, 512]:
        output = ctypes.create_string_buffer(megabytes * 1024 ** 2)
        count = function(output, len(output), source, len(data), None, 0x801)
        if count and count < len(output):
            return output.raw[:count], 'lzfse'
    raise ValueError('LZFSE decoding failed or output exceeds the 512 MiB bound')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--record', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.exit(2, 'Use a new output file\n')
    body, container = payload(args.input.read_bytes())
    decoded, compression = decode(body)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(decoded)
    arches = macho_architectures(args.output)
    if not arches:
        parser.exit(2, 'Decoded data is not a recognized Mach-O; do not infer architecture\n')
    record = {'input_name': args.input.name, 'input_sha256': sha256(args.input),
              'output_name': args.output.name, 'output_sha256': sha256(args.output),
              'output_size': len(decoded), 'container': container, 'compression': compression,
              'architectures': arches, 'runtime_verification': 'NOT_RUN'}
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
