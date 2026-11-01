"""Check that partial/corrupt archives cannot become verified evidence."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import prepare_installer
import unpack_kernel
import serve_shared_support


def xar(data=b'payload', corrupt=False):
    digest = '0' * 40 if corrupt else hashlib.sha1(data).hexdigest()
    xml = ('<xar><toc>' + ''.join(
        '<file><name>{}</name><data><offset>0</offset><length>{}</length>'
        '<encoding style="application/octet-stream"/>'
        '<archived-checksum style="sha1">{}</archived-checksum></data></file>'.format(name, len(data), digest)
        for name in ['Payload', 'SharedSupport.dmg']) + '</toc></xar>').encode()
    toc = zlib.compress(xml)
    return struct.pack('>4sHHQQI', b'xar!', 28, 1, len(toc), len(xml), 1) + toc + data


class ArchiveBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'installer.pkg'

    def test_valid_member_hash(self):
        self.path.write_bytes(xar())
        entry = prepare_installer.entries(self.path)['Payload']
        record = prepare_installer.extract(self.path, entry, self.path.parent / 'Payload')
        self.assertEqual(record['xar_sha1'], hashlib.sha1(b'payload').hexdigest())

    def test_truncated_package_rejected(self):
        self.path.write_bytes(xar()[:-3])
        with self.assertRaises(ValueError):
            prepare_installer.entries(self.path)

    def test_corrupt_member_rejected(self):
        self.path.write_bytes(xar(corrupt=True))
        entry = prepare_installer.entries(self.path)['Payload']
        with self.assertRaises(ValueError):
            prepare_installer.extract(self.path, entry, self.path.parent / 'Payload')

    def test_existing_extraction_preserved(self):
        self.path.write_bytes(xar())
        output = self.path.parent / 'Payload'
        output.write_bytes(b'existing')
        with self.assertRaises(ValueError):
            prepare_installer.extract(self.path, prepare_installer.entries(self.path)['Payload'], output)
        self.assertEqual(output.read_bytes(), b'existing')

    def test_der_out_of_bounds_rejected(self):
        with self.assertRaises(ValueError):
            list(unpack_kernel.der_items(b'\x30\x08\x00'))

    def test_der_indefinite_length_rejected(self):
        with self.assertRaises(ValueError):
            list(unpack_kernel.der_items(b'\x30\x80'))

    def test_im4p_payload_extracted(self):
        content = b'\x16\x04IM4P\x16\x04krnl\x16\x01x\x04\x03abc'
        body, container = unpack_kernel.payload(b'\x30' + bytes([len(content)]) + content)
        self.assertEqual((body, container), (b'abc', 'IM4P'))

    def test_unrecognized_compression_rejected(self):
        with self.assertRaises(ValueError):
            unpack_kernel.decode(b'unknown')

    def test_exact_http_range(self):
        self.assertEqual(serve_shared_support.byte_range('bytes=0-0', 100), (0, 0, 206))

    def test_suffix_http_range(self):
        self.assertEqual(serve_shared_support.byte_range('bytes=-20', 100), (80, 99, 206))

    def test_open_ended_http_range(self):
        self.assertEqual(serve_shared_support.byte_range('bytes=90-', 100), (90, 99, 206))

    def test_invalid_http_range_rejected(self):
        for value in ['bytes=100-', 'bytes=1-0', 'bytes=-0', 'bytes=0-1,3-4']:
            with self.assertRaises(ValueError):
                serve_shared_support.byte_range(value, 100)


if __name__ == '__main__':
    unittest.main()
