#!/usr/bin/env bash
# Render build script - installs Python deps + builds Next.js
set -euo pipefail

echo "=== Installing Python dependencies ==="
pip3 install --quiet -r requirements.txt

echo "=== Installing Node dependencies (including devDependencies) ==="
npm install --include=dev

echo "=== Building Next.js ==="
npm run build

echo "=== Copying scripts directory to standalone output ==="
mkdir -p .next/standalone/scripts
cp -r scripts/wv_process.py .next/standalone/scripts/
cp -r scripts/widevine_termux .next/standalone/scripts/

echo "=== Build complete ==="
