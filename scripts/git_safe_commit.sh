#!/usr/bin/env bash
set -euo pipefail

# Skrip untuk commit file data lokal dari dalam GitHub Actions dengan mekanisme retry
# Usage: scripts/git_safe_commit.sh "Commit message"

MSG="${1:-"chore: update data files [auto commit]"}"
RETRIES=5
SLEEP=2

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

for i in $(seq 1 $RETRIES); do
  echo "[git_safe_commit] Attempt $i/$RETRIES"

  # pastikan kita di branch utama
  git checkout main || git checkout -B main

  # ambil perubahan remote dan rebase lokal
  git pull --rebase origin main || true

  # tambahkan file data jika ada perubahan
  git add data/*.json || true

  if git diff --staged --quiet; then
    echo "[git_safe_commit] Tidak ada perubahan pada data/*.json. Tidak ada commit."
    exit 0
  fi

  # commit
  git commit -m "$MSG" || true

  # coba push
  if git push origin main; then
    echo "[git_safe_commit] Push berhasil."
    exit 0
  else
    echo "[git_safe_commit] Push gagal, mencoba lagi setelah sleep $SLEEP..."
    sleep $SLEEP
  fi
done

echo "[git_safe_commit] Gagal melakukan push setelah $RETRIES percobaan." >&2
exit 1
