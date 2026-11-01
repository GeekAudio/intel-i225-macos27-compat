#!/usr/bin/env python3
"""Expose the raw SharedSupport member to a local read-only image mounter.

This avoids a second 18 GB copy. Verify the full package with apple_installer.py
first. Serving an existing file does not independently verify its checksum.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from prepare_installer import entries


def byte_range(value, size):
    if value is None:
        return 0, size - 1, 200
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
    if not match or not any(match.groups()):
        raise ValueError('Unsupported range')
    first, last = match.groups()
    start = int(first) if first else max(0, size - int(last))
    end = min(int(last), size - 1) if first and last else size - 1
    if not 0 <= start <= end < size:
        raise ValueError('Unsatisfiable range')
    return start, end, 206


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--ready-file', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    initial = args.package.stat()
    if not (manifest.get('catalog_digest_match') or manifest.get('artifact_integrity_verified')) or initial.st_size != manifest.get('actual_size'):
        parser.exit(2, 'A completed download and its verification manifest are required\n')
    member = entries(args.package)['SharedSupport.dmg']

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def do_HEAD(self):
            self.respond(False)

        def do_GET(self):
            self.respond(True)

        def respond(self, body):
            if self.path != '/SharedSupport.dmg':
                self.send_error(404)
                return
            current = args.package.stat()
            if (current.st_size, current.st_mtime_ns) != (initial.st_size, initial.st_mtime_ns):
                self.send_error(503, 'Source package changed')
                return
            try:
                start, end, status = byte_range(self.headers.get('Range'), member['size'])
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', 'bytes */{}'.format(member['size']))
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            self.send_response(status)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Type', 'application/x-apple-diskimage')
            self.send_header('Content-Length', str(end - start + 1))
            self.send_header('ETag', '"{}"'.format(member['sha1']))
            if status == 206:
                self.send_header('Content-Range', 'bytes {}-{}/{}'.format(start, end, member['size']))
            self.end_headers()
            if body:
                with args.package.open('rb') as source:
                    source.seek(member['offset'] + start)
                    remaining = end - start + 1
                    try:
                        while remaining:
                            block = source.read(min(1024 ** 2, remaining))
                            if not block:
                                break
                            self.wfile.write(block)
                            remaining -= len(block)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    url = 'http://127.0.0.1:{}/SharedSupport.dmg'.format(server.server_port)
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    args.ready_file.write_text(json.dumps({'url': url, 'shared_support_bytes': member['size'],
                                         'read_only': True, 'listen_address': '127.0.0.1'}, indent=2) + '\n')
    print(url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
