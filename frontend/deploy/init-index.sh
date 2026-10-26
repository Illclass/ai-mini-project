#!/usr/bin/env bash
set -euo pipefail
complete() {
  for name in law msds; do
    test -s "$1/$name/index.faiss" && test -s "$1/$name/index.pkl" || return 1
  done
}
if complete faiss_db; then
  echo 'Saved indexes found; preserving the existing volume.'
elif complete /seed; then
  echo 'Copying trusted local indexes into the separate Compose volume.'
  cp -R /seed/law /seed/msds faiss_db/
else
  echo 'No complete index found; ingesting repository PDFs (first start can take several minutes).'
  bash ingest_all.sh
fi
