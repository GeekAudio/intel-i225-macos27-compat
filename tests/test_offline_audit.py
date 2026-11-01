"""Synthetic test inputs verify reporting boundaries; they are not OS evidence."""
import importlib.util
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load('offline_audit')
installer = load('apple_installer')


def thin(cpu=0x01000007, subtype=3):
    return struct.pack('<8I', 0xfeedfacf, cpu, subtype, 11, 0, 0, 0, 0)


class OfflineAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'target'
        self.kext = Path(self.temp.name) / 'candidate.kext'
        version = self.root / 'System/Library/CoreServices/SystemVersion.plist'
        version.parent.mkdir(parents=True)
        version.write_bytes(plistlib.dumps({'ProductVersion': '27.2', 'ProductBuildVersion': '26B123'}))
        (self.kext / 'Contents/MacOS').mkdir(parents=True)
        (self.kext / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'test.candidate', 'CFBundleExecutable': 'test',
            'CFBundleVersion': '1.0', 'OSBundleLibraries': {}}))
        self.binary = self.kext / 'Contents/MacOS/test'
        self.binary.write_bytes(thin())

    def run_audit(self, **kw):
        args = dict(root=self.root, kext=self.kext, arch='x86_64', scope='system',
                    expected_version='27.2', expected_build='26B123')
        args.update(kw)
        return audit.audit(**args)

    def test_thin_x86(self):
        self.assertEqual(audit.macho_architectures(self.binary), ['x86_64'])

    def test_arm64e_is_not_arm64(self):
        self.binary.write_bytes(thin(0x0100000c, 2))
        self.assertEqual(audit.macho_architectures(self.binary), ['arm64e'])

    def test_universal_slices(self):
        h = struct.pack('>II', 0xcafebabe, 2)
        h += struct.pack('>IIIII', 0x01000007, 3, 48, 32, 0)
        h += struct.pack('>IIIII', 0x0100000c, 2, 80, 32, 0)
        self.binary.write_bytes(h + thin() + thin(0x0100000c, 2))
        self.assertEqual(audit.macho_architectures(self.binary), ['arm64e', 'x86_64'])

    def test_truncated_header_is_unknown(self):
        self.binary.write_bytes(thin()[:12])
        self.assertEqual(audit.macho_architectures(self.binary), [])

    def test_fat_header_cannot_claim_missing_slice(self):
        self.binary.write_bytes(struct.pack('>II', 0xcafebabe, 1) +
                                struct.pack('>IIIII', 0x01000007, 3, 1024, 32, 0))
        self.assertEqual(audit.macho_architectures(self.binary), [])

    def test_absent_kernel_is_incomplete(self):
        result = self.run_audit()
        self.assertEqual(result['status'], 'STATIC_INCOMPLETE')
        self.assertEqual(result['runtime_verification'], 'NOT_RUN')

    def test_kernel_architecture_mismatch_blocks_static_path(self):
        kernel = self.root / 'System/Library/Kernels/kernel'
        kernel.parent.mkdir(parents=True)
        kernel.write_bytes(thin(0x0100000c, 2))
        self.assertEqual(self.run_audit()['status'], 'STATIC_BLOCKED')

    def test_recovery_does_not_prove_installed_system_mismatch(self):
        kernel = self.root / 'System/Library/Kernels/kernel'
        kernel.parent.mkdir(parents=True)
        kernel.write_bytes(thin(0x0100000c, 2))
        result = self.run_audit(scope='recovery')
        self.assertEqual(result['status'], 'STATIC_INCOMPLETE')

    def test_wrong_target_version_rejected(self):
        with self.assertRaises(ValueError):
            self.run_audit(expected_version='27.0.1')

    def test_candidate_architecture_mismatch(self):
        self.binary.write_bytes(thin(0x0100000c, 2))
        self.assertEqual(self.run_audit()['status'], 'STATIC_BLOCKED')

    def test_missing_dependency_stays_unresolved(self):
        p = self.kext / 'Contents/Info.plist'
        info = plistlib.loads(p.read_bytes())
        info['OSBundleLibraries'] = {'test.dependency': '1.0'}
        p.write_bytes(plistlib.dumps(info))
        result = self.run_audit()
        self.assertEqual(result['dependencies'][0]['status'], 'UNRESOLVED_OFFLINE')

    def test_prerelease_version_order(self):
        self.assertLess(audit.bundle_version('1.0.3b2'), audit.bundle_version('1.0.3'))
        self.assertGreater(audit.bundle_version('2.0'), audit.bundle_version('1.9.9'))
        self.assertIsNone(audit.bundle_version('unknown'))

    def test_non_apple_download_url_rejected(self):
        for url in ['http://swcdn.apple.com/pkg', 'https://apple.com.evil.example/pkg',
                    'https://token@swcdn.apple.com/pkg']:
            with self.assertRaises(ValueError):
                installer.apple_url(url)


if __name__ == '__main__':
    unittest.main()
