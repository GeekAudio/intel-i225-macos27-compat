#!/usr/bin/env python3
"""Read an explicitly supplied offline macOS image. Never modify EFI or load a kext."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import plistlib
import re
import struct


def macho_architectures(path):
    """Return slices from bounded Mach-O headers in a Path or bytes value."""
    cpus = {0x01000007: 'x86_64', 0x0100000c: 'arm64'}
    def name(cpu, subtype):
        if cpu == 0x0100000c and subtype & 0x00ffffff == 2:
            return 'arm64e'
        return cpus.get(cpu, 'cpu-{:x}'.format(cpu))
    memory = isinstance(path, (bytes, bytearray))
    with (io.BytesIO(path) if memory else path.open('rb')) as stream:
        size = len(path) if memory else path.stat().st_size
        header = stream.read(8)
        if len(header) != 8:
            return []
        magic = header[:4]
        if magic in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf'):
            tail = stream.read(24)
            if len(tail) != 24:
                return []
            endian = '<' if magic == b'\xcf\xfa\xed\xfe' else '>'
            cpu, subtype = struct.unpack(endian + 'II', (header + tail)[4:12])
            return [name(cpu, subtype)]
        formats = {b'\xca\xfe\xba\xbe': ('>', 20), b'\xbe\xba\xfe\xca': ('<', 20),
                   b'\xca\xfe\xba\xbf': ('>', 32), b'\xbf\xba\xfe\xca': ('<', 32)}
        if magic not in formats:
            return []  # compressed/encrypted/IMG4 data is unknown, not an absent CPU
        endian, stride = formats[magic]
        count = struct.unpack(endian + 'I', header[4:8])[0]
        if not 1 <= count <= 64 or 8 + count * stride > size:
            return []
        found = []
        for _ in range(count):
            record = stream.read(stride)
            cpu, subtype = struct.unpack(endian + 'II', record[:8])
            offset, length = struct.unpack(endian + ('II' if stride == 20 else 'QQ'), record[8:16] if stride == 20 else record[8:24])
            if offset < 8 + count * stride or length < 32 or offset + length > size:
                return []
            position = stream.tell()
            stream.seek(offset)
            inner = stream.read(12)
            stream.seek(position)
            if inner[:4] not in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf'):
                return []
            inner_endian = '<' if inner[:4] == b'\xcf\xfa\xed\xfe' else '>'
            if struct.unpack(inner_endian + 'II', inner[4:12]) != (cpu, subtype):
                return []
            found.append(name(cpu, subtype))
        return sorted(set(found))


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_plist(path):
    with path.open('rb') as stream:
        value = plistlib.load(stream)
    if not isinstance(value, dict):
        raise ValueError('Expected a plist dictionary')
    return value


def bundle_version(value):
    match = re.fullmatch(r'(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:(d|a|b|fc)(\d+))?', value)
    if not match:
        return None
    groups = match.groups()
    return tuple(int(x or 0) for x in groups[:3]) + ({'d': 0, 'a': 1, 'b': 2, 'fc': 3, None: 4}[groups[3]], int(groups[4] or 0))


def inside(root, path):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def audit(root, kext, arch, scope, expected_version, expected_build):
    root, kext = root.resolve(), kext.resolve()
    version = read_plist(root / 'System/Library/CoreServices/SystemVersion.plist')
    if version.get('ProductVersion') != expected_version or version.get('ProductBuildVersion') != expected_build:
        raise ValueError('Mounted image version/build does not match the pinned target')
    info = read_plist(kext / 'Contents/Info.plist')
    executable_name = info['CFBundleExecutable']
    if Path(executable_name).name != executable_name:
        raise ValueError('Invalid kext executable name')
    binary = kext / 'Contents/MacOS' / executable_name
    candidate_arches = macho_architectures(binary)
    blocked, unknown = [], []
    if not candidate_arches:
        unknown.append('Candidate Mach-O architectures could not be established')
    elif arch not in candidate_arches:
        blocked.append('Candidate does not contain the requested architecture')
    inventory, errors = {}, []
    extensions = root / 'System/Library/Extensions'
    for path in sorted(extensions.rglob('Info.plist')):
        if path.parent.name != 'Contents' or not inside(root, path):
            continue
        try:
            data = read_plist(path)
            identifier = data.get('CFBundleIdentifier')
            if identifier:
                exe = data.get('CFBundleExecutable')
                candidate = path.parent / 'MacOS' / exe if isinstance(exe, str) and Path(exe).name == exe else None
                inventory.setdefault(identifier, []).append({
                    'version': str(data.get('CFBundleVersion', '')),
                    'plist': str(path.relative_to(root)),
                    'architectures': macho_architectures(candidate) if candidate and candidate.is_file() and inside(root, candidate) else [],
                    'executable_present': bool(candidate and candidate.is_file() and inside(root, candidate)),
                })
        except (OSError, ValueError, plistlib.InvalidFileException) as error:
            errors.append({'path': str(path.relative_to(root)), 'error_type': type(error).__name__})
    dependencies = []
    for identifier, minimum in sorted(info.get('OSBundleLibraries', {}).items()):
        providers = inventory.get(identifier, [])
        required = bundle_version(minimum)
        satisfied = any(required is not None and bundle_version(p['version']) is not None
                        and bundle_version(p['version']) >= required and arch in p['architectures'] for p in providers)
        dependencies.append({'identifier': identifier, 'minimum': minimum, 'providers': providers,
                             'status': 'PLIST_VERSION_AND_ARCH_PRESENT' if satisfied else 'UNRESOLVED_OFFLINE'})
        if not satisfied:
            unknown.append('Dependency requires target collection/linker verification: ' + identifier)
    kernels = []
    for directory in ['System/Library/Kernels', 'System/Library/KernelCollections']:
        base = root / directory
        if base.is_dir():
            for path in sorted(base.rglob('*')):
                if path.is_file() and inside(root, path):
                    arches = macho_architectures(path)
                    kernels.append({'path': str(path.relative_to(root)), 'architectures': arches,
                                    'sha256': sha256(path)})
    known = [p for p in kernels if p['architectures']]
    opaque = [p for p in kernels if not p['architectures']]
    if scope != 'system':
        unknown.append('Recovery image is not evidence of the complete installed OS')
    elif known and not opaque and not any(arch in p['architectures'] for p in known):
        blocked.append('Requested CPU architecture is absent from the scanned kernel/collection headers')
    elif not any(arch in p['architectures'] for p in known):
        unknown.append('A target kernel/collection with the requested architecture was not established')
    if not kernels:
        unknown.append('No kernel/collection files were found in the supplied image')
    if errors:
        unknown.append('Some target extension plists could not be read')
    status = 'STATIC_BLOCKED' if blocked else ('STATIC_INCOMPLETE' if unknown else 'STATIC_PREREQUISITES_ONLY')
    return {'schema_version': 1, 'status': status, 'runtime_verification': 'NOT_RUN',
            'target': {'version': expected_version, 'build': expected_build, 'requested_arch': arch, 'scope': scope},
            'candidate': {'bundle_id': info.get('CFBundleIdentifier'), 'version': info.get('CFBundleVersion'),
                          'sha256': sha256(binary), 'architectures': candidate_arches},
            'kernel_artifacts': kernels, 'dependencies': dependencies, 'inventory_bundle_count': len(inventory),
            'blocked': blocked, 'unresolved': unknown, 'read_errors': errors,
            'limits': ['Bundle presence and version do not prove symbol or C++ ABI compatibility.',
                       'This audit does not load a driver, validate bootability, or test network hardware.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--kext', type=Path, required=True)
    parser.add_argument('--arch', choices=['x86_64', 'arm64', 'arm64e'], required=True)
    parser.add_argument('--scope', choices=['system', 'recovery'], required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--build', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.root, args.kext, args.arch, args.scope, args.version, args.build)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        print(result['status'])
        return {'STATIC_BLOCKED': 3, 'STATIC_INCOMPLETE': 1, 'STATIC_PREREQUISITES_ONLY': 0}[result['status']]
    except (OSError, ValueError, KeyError, plistlib.InvalidFileException, struct.error) as error:
        parser.exit(2, 'ERROR: {}\n'.format(error))


if __name__ == '__main__':
    raise SystemExit(main())
