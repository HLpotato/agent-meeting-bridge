#!/bin/sh
# Agent Meeting Bridge - start the meeting (macOS / Linux)
# Run this in your PRIVATE mailbox copy (not the public template).
cd "$(dirname "$0")" || exit 1
command -v python3 >/dev/null 2>&1 || { echo "Python 3 is not installed."; exit 1; }
if [ ! -f bridge/bridge.config.json ]; then
  echo "First run: copying the example config. Edit bridge/bridge.config.json"
  echo "and set project_dir to your project folder, then run this file again."
  cp bridge/bridge.config.example.json bridge/bridge.config.json
  exit 0
fi
exec python3 bridge/bridge.py
