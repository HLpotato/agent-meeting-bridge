#!/usr/bin/env python3
"""A fake Gemini CLI for local tests. Mimics the real contract:
gemini -p "<prompt>" --output-format json [--resume <id>] prints JSON with
`response` and `session_id`. Logs invocations to calls.log like fake_agent."""

import json
import sys
from pathlib import Path

args = sys.argv[1:]
prompt = ""
if "-p" in args:
    prompt = args[args.index("-p") + 1]
resumed = "--resume" in args

here = Path(__file__).resolve().parent
with open(here / "calls.log", "a", encoding="utf-8") as f:
    f.write(json.dumps({"agent": "gemini", "prompt": prompt, "resumed": resumed}) + "\n")

print(json.dumps({
    "response": f"Fake Gemini reply. Prompt was: {prompt} (resumed={resumed})",
    "session_id": "fake-gemini-session-001",
}))
