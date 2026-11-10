#!/bin/bash
# WebTack — Double-clickable launcher for macOS
# Starts the local server and opens the vault in your default browser.

cd "$(dirname "$0")"

echo "=========================================================="
echo "    WebTack — Personal Local Knowledge Vault & Studio     "
echo "=========================================================="
echo "🚀 Starting local server at http://127.0.0.1:8080 ..."
echo "🌐 Opening your browser..."
echo "ℹ️  Press Ctrl+C in this window at any time to quit."
echo "=========================================================="
echo ""

python3 curate.py view --server
