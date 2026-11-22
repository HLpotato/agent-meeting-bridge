#!/usr/bin/env python3
"""A fake worker agent for local tests. Mimics the Claude Code headless
contract: reads the -p prompt, prints JSON with `result` and `session_id`.
Also appends every invocation to calls.log next to this file, so tests can
prove a message was never run twice."""

import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
prompt = ""
if "-p" in args:
    prompt = args[args.index("-p") + 1]
resumed = "--resume" in args

here = Path(__file__).resolve().parent
with open(here / "calls.log", "a", encoding="utf-8") as f:
    f.write(json.dumps({"agent": "claude", "prompt": prompt, "resumed": resumed,
                        "cwd": os.getcwd()}) + "\n")

print(json.dumps({
    "result": f"Fake reply. Prompt was: {prompt} (resumed={resumed})",
    "session_id": "fake-session-001",
}))
