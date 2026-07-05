#!/usr/bin/env python3
"""Script kecil untuk dijalankan di CI/cron yang membersihkan koleksi `used_clips` di Firestore."""
import argparse
from firebase_connector import cleanup_used_clips

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90, help="Hapus entri lebih tua dari N hari")
    args = parser.parse_args()
    cleanup_used_clips(days=args.days)

if __name__ == '__main__':
    main()
