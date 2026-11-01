"""Synthetic chunklists and CLI strings test validation logic, not Apple trust."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from verify_integrity import chunk_records, verify_file
from apple_signature import trusted_apple_signature
import apple_installer


def fixture(data):
    header = struct.pack('<4sI4BQQQ', b'CNKL', 36, 1, 1, 2, 0, 1, 36, 72)
    body = header + struct.pack('<I', len(data)) + hashlib.sha256(data).digest()
    return body + hashlib.sha256(body).digest()


class IntegrityTests(unittest.TestCase):
    def test_valid_chunk_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data'
            path.write_bytes(b'payload')
            self.assertTrue(verify_file(path, fixture(b'payload'), 7)['all_chunk_sha256_match'])

    def test_corrupt_chunk_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data'
            path.write_bytes(b'PAYLOAD')
            with self.assertRaises(ValueError):
                verify_file(path, fixture(b'payload'), 7)

    def test_corrupt_trailer_rejected(self):
        with self.assertRaises(ValueError):
            chunk_records(fixture(b'payload')[:-1] + b'x')

    def test_software_update_certificate_status_supported(self):
        output = 'Status: signed Apple Software\n1. Software Update\n3. Apple Root CA'
        self.assertTrue(trusted_apple_signature(0, output))

    def test_developer_id_status_not_accepted_as_apple_software(self):
        self.assertFalse(trusted_apple_signature(0, 'Status: signed Developer ID\nApple Root CA'))
        self.assertFalse(trusted_apple_signature(1, 'Status: signed Apple Software\nApple Root CA'))

    def test_failed_redownload_clears_previous_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'target.json'
            manifest.write_text(json.dumps({'version': '27.2', 'build': '26B123',
                'package': {'URL': 'https://swcdn.apple.com/example/InstallAssistant.pkg',
                            'Size': 7, 'Digest': '0' * 40},
                'artifact_integrity_verified': True, 'catalog_digest_match': True,
                'all_chunk_sha256_match': True, 'package_signature_exit': 0}))
            (root / 'InstallAssistant-27.2-26B123.pkg').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                apple_installer.download(manifest, root)
            result = json.loads(manifest.read_text())
            self.assertFalse(result['artifact_integrity_verified'])
            self.assertFalse(result['catalog_digest_match'])
            self.assertNotIn('package_signature_exit', result)


if __name__ == '__main__':
    unittest.main()
