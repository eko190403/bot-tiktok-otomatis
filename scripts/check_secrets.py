#!/usr/bin/env python3
import re
import sys

# Very small heuristic secret scanner for pre-commit
PATTERNS = [
    r"-----BEGIN PRIVATE KEY-----",
    r"""AIza[0-9A-Za-z_-]{35}""",
    r"client_secret\"?\s*:\s*\"[A-Za-z0-9_\-]{10,}\"",
    r"access_token\"?\s*:\s*\"[A-Za-z0-9_\-]{10,}\"",
    r"refresh_token\"?\s*:\s*\"[A-Za-z0-9_\-]{10,}\"",
    r"-----BEGIN RSA PRIVATE KEY-----",
]

def scan_file(path):
    try:
        data = open(path, "rb").read()
    except Exception:
        return []
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return []

    matches = []
    for p in PATTERNS:
        if re.search(p, text):
            matches.append(p)
    return matches

def main(argv):
    any_found = False
    for path in argv[1:]:
        matches = scan_file(path)
        if matches:
            any_found = True
            print(f"[secret-scan] Possible secret in {path}: {matches}")

    if any_found:
        print("\nSecret scanner blocked commit. Move secrets to GitHub Secrets.")
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
