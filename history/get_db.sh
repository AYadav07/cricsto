#!/usr/bin/env bash
# Download history/history.duckdb (pre-2002 scorecard database) from the data-latest release.
# Separate from cricsheet/scripts/get_db.sh. The file was uploaded by hand once; it doesn't change.
#
# Usage: bash history/get_db.sh   (from anywhere; writes history/history.duckdb)
set -euo pipefail

cd "$(dirname "$0")"                      # the history/ folder
REPO="AYadav07/cricsto"
TAG="data-latest"

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "Downloading history database with gh ..."
  gh release download "$TAG" -R "$REPO" -p history.duckdb --clobber
else
  echo "Downloading history database from the public link ..."
  if ! curl -fL --retry 3 -o history.duckdb "https://github.com/$REPO/releases/download/$TAG/history.duckdb"; then
    echo "Download failed. Check that history.duckdb is attached to the $TAG release," >&2
    echo "or build it locally: python history/build.py (needs history/raw/, see history/README.md)" >&2
    exit 1
  fi
fi
echo "Done: history/history.duckdb"
