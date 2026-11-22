#!/usr/bin/env python3
"""Chair-side helper: send the next numbered message into the mailbox.

Used by the chair agent (e.g. Muse) or by the human directly. Computes the
next free number across in/ and out/, writes in/NNN-<slug>.md, and - when the
mailbox is a git repo with a remote - commits and pushes it.

Usage:
    python tools/send_message.py "Your message text"
    python tools/send_message.py --file message.md
    python tools/send_message.py --slug rootword-question "Your message text"

The human's approval rule is NOT enforced by this script - whoever chairs the
meeting must get the human's go-ahead for new work instructions before
sending, per PROTOCOL.md.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NUM_RE = re.compile(r"^(\d{3,})-")


def next_number() -> int:
    highest = 0
    for folder in ("in", "out"):
        d = ROOT / folder
        if d.is_dir():
            for path in d.iterdir():
                m = NUM_RE.match(path.name)
                if m:
                    highest = max(highest, int(m.group(1)))
    return highest + 1


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:40] or "message").rstrip("-")


def git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=str(ROOT), capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a numbered meeting message")
    parser.add_argument("text", nargs="?", help="message text")
    parser.add_argument("--file", help="read the message text from this file instead")
    parser.add_argument("--slug", help="short slug for the filename (default: from the text)")
    parser.add_argument("--to", dest="to", default=None,
                        help="agent this message is addressed to (e.g. claude, gemini). "
                             "Default: the bridge's default agent. Adds a 'To:' routing line.")
    parser.add_argument("--no-push", action="store_true", help="write only; do not commit/push")
    args = parser.parse_args()

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8").strip()
    elif args.text:
        text = args.text.strip()
    else:
        print("Give message text or --file.", file=sys.stderr)
        return 2
    if not text:
        print("Message is empty.", file=sys.stderr)
        return 2

    slug = slugify(args.slug or text.split("\n")[0])
    if args.to:
        text = f"To: {args.to.strip().lower()}\n\n{text}"
    number = next_number()
    path = ROOT / "in" / f"{number:03d}-{slug}.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)}")

    if not args.no_push and git(["rev-parse", "--git-dir"]).returncode == 0:
        git(["add", str(path.relative_to(ROOT))])
        git(["commit", "-m", f"meeting: message #{number:03d}"])
        if git(["remote"]).stdout.strip():
            result = git(["push"])
            if result.returncode != 0:
                print(f"Push failed (message is committed locally): {result.stderr.strip()}",
                      file=sys.stderr)
                return 1
            print(f"Pushed message #{number:03d}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
