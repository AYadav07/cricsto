#!/usr/bin/env bash
# Download the latest database built by the "Refresh data" GitHub Action.
# Replaces cricsheet/data/cricsto.duckdb. Close other connections to it (DBeaver, duckdb CLI) first.
#
# Works for a public or private repo:
#   - signed in to the GitHub CLI (gh auth login) → downloads with your login
#   - otherwise → public download link (public repo only)
#
# Usage: bash cricsheet/scripts/get_db.sh   (from anywhere; writes into cricsheet/data/)
set -euo pipefail

cd "$(dirname "$0")/.."                   # the cricsheet/ folder
REPO="AYadav07/cricsto"
TAG="data-latest"
mkdir -p data

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "Downloading database with gh ..."
  gh release download "$TAG" -R "$REPO" -p cricsto.duckdb.gz -p manifest.json -D data --clobber
else
  echo "Downloading database from the public link ..."
  URL="https://github.com/$REPO/releases/download/$TAG"
  if ! curl -fL --retry 3 -o data/cricsto.duckdb.gz "$URL/cricsto.duckdb.gz"; then
    echo "Download failed. If the repo is private, install the GitHub CLI and run: gh auth login" >&2
    exit 1
  fi
  curl -fsSL --retry 3 -o data/manifest.json "$URL/manifest.json"
fi

gunzip -f data/cricsto.duckdb.gz          # → cricsheet/data/cricsto.duckdb
echo "Done. Data summary:"
cat data/manifest.json
