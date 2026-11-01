"""Recognize pkgutil's trusted Apple package status, including Software Update certs."""


def trusted_apple_signature(returncode, output):
    return (returncode == 0 and 'Status: signed Apple Software' in output
            and 'Apple Root CA' in output)
