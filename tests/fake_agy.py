#!/usr/bin/env python3
"""A fake Antigravity CLI (`agy`) for local tests. Mimics the real contract:
agy -p "<prompt>" --output-format json [--conversation <id>] prints a JSON
envelope with `status`, `response` and `conversation_id`. Logs to calls.log."""

import json
import sys
from pathlib import Path

args = sys.argv[1:]
prompt = ""
if "-p" in args:
    prompt = args[args.index("-p") + 1]
resumed = "--conversation" in args

here = Path(__file__).resolve().parent
with open(here / "calls.log", "a", encoding="utf-8") as f:
    f.write(json.dumps({"agent": "agy", "prompt": prompt, "resumed": resumed}) + "\n")

print(json.dumps({
    "status": "SUCCESS",
    "response": f"Fake agy reply. Prompt was: {prompt} (resumed={resumed})",
    "conversation_id": "fake-conversation-001",
}))
