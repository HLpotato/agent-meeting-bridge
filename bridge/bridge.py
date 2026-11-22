#!/usr/bin/env python3
"""Agent Meeting Bridge - PC side.

Polls a git "mailbox" repo for numbered messages in in/, runs each one as a
turn of a local agent CLI (v1 adapter: Claude Code headless mode), writes the
reply to out/, and commits/pushes everything back so the other agent (and the
human chairing the meeting) can read it.

Design rules (see PROTOCOL.md):
- One turn at a time, in number order. Nothing crosses, nothing runs twice.
- A message number is recorded as started BEFORE the agent runs, so a crash
  never causes a silent duplicate run; a started-but-unfinished number gets
  an error reply file instead.
- Standard library only. Requires: python 3.10+, git, and the agent CLI.

Usage:
    python bridge.py [--config bridge.config.json] [--once]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent  # the mailbox repo root (template layout: bridge/ under root)

MESSAGE_RE = re.compile(r"^(\d{3,})-.*\.md$")
TO_RE = re.compile(r"^To:\s*([A-Za-z0-9_-]+)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_addressee(text: str, default: str) -> tuple[str, str]:
    """A message may start with a `To: <agent>` line. Returns (agent, prompt
    with the routing line removed). No To: line = the default agent."""
    lines = text.split("\n")
    for i, line in enumerate(lines[:3]):
        m = TO_RE.match(line.strip())
        if m:
            del lines[i]
            return m.group(1).lower(), "\n".join(lines).strip()
    return default, text


def agents_config(config: dict) -> dict:
    """Agent table from config. Falls back to the legacy single-agent shape:
    {"claude": {"command": agent_command, "adapter": "claude"}}."""
    agents = config.get("agents")
    if isinstance(agents, dict) and agents:
        return {str(name).lower(): spec for name, spec in agents.items()}
    return {"claude": {"command": config.get("agent_command", "claude"),
                       "adapter": "claude"}}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(f"[{now_iso()}] {msg}", flush=True)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run(cmd: list[str], cwd: Path, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def git(args: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess:
    result = run(["git"] + args, cwd=cwd)
    if check and result.returncode != 0:
        log(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def git_sync_in(repo: Path) -> None:
    """Pull new messages. No remote (local test) is fine - skip quietly."""
    if git(["remote"], cwd=repo).stdout.strip():
        git(["pull", "--ff-only"], cwd=repo, check=True)


def git_push_out(repo: Path, message: str) -> None:
    """Commit mailbox changes and push if a remote exists. Best effort."""
    git(["add", "in", "out", "status.json"], cwd=repo)
    if git(["status", "--porcelain"], cwd=repo).stdout.strip():
        git(["commit", "-m", message], cwd=repo, check=True)
    if git(["remote"], cwd=repo).stdout.strip():
        git(["push"], cwd=repo, check=True)


def write_status(repo: Path, state: str, number: int | None, detail: str = "") -> None:
    save_json(repo / "status.json", {
        "state": state,               # idle | agent-working | done | error
        "message": number,            # message number the state refers to
        "detail": detail,
        "updated_at": now_iso(),
    })


def list_messages(repo: Path) -> list[tuple[int, Path]]:
    found = []
    in_dir = repo / "in"
    if in_dir.is_dir():
        for path in sorted(in_dir.iterdir()):
            m = MESSAGE_RE.match(path.name)
            if m:
                found.append((int(m.group(1)), path))
    return sorted(found)


def call_agent(config: dict, agent_name: str, prompt: str,
               session_id: str | None) -> tuple[str, str | None]:
    """Run one turn of the named agent. Returns (reply_text, new_session_id).

    Adapters (same shape: headless prompt in, JSON out, resumable):
    - claude:  claude -p "<prompt>" --output-format json [--resume <id>]
               JSON carries `result` and `session_id`.
    - gemini:  gemini -p "<prompt>" --output-format json [--resume <id>]
               JSON carries `response` and `session_id`.
               NOTE: Gemini CLI stopped serving individual / free / Google AI
               Pro & Ultra accounts on 18 Jun 2026 (Google moved them to
               Antigravity CLI). It still works with enterprise Code Assist
               licences and paid Gemini API keys. For an individual's Gemini
               seat, use the agy adapter below.
    - agy:     agy -p "<prompt>" --output-format json [--conversation <id>]
               (Google Antigravity CLI, the successor for individuals.)
               JSON envelope carries `response`, `status` and
               `conversation_id` (the resume id - there is no --resume flag).
    """
    agents = agents_config(config)
    spec = agents.get(agent_name)
    if spec is None:
        raise RuntimeError(f"unknown agent '{agent_name}' (configured: {', '.join(sorted(agents))})")
    adapter = str(spec.get("adapter", agent_name)).lower()
    command = str(spec.get("command", agent_name))
    cmd = [command, "-p", prompt, "--output-format", "json"]
    if session_id:
        cmd += ["--conversation", session_id] if adapter == "agy" else ["--resume", session_id]
    timeout = int(config.get("turn_timeout_seconds", 1800))
    result = run(cmd, cwd=Path(config["project_dir"]).expanduser(), timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"{agent_name} command exited {result.returncode}: {result.stderr.strip()[:500]}")
    reply_field = "response" if adapter in ("gemini", "agy") else "result"
    try:
        payload = json.loads(result.stdout)
        if adapter == "agy" and payload.get("status") not in (None, "SUCCESS"):
            raise RuntimeError(f"{agent_name} run status was {payload.get('status')}: "
                               f"{str(payload.get('error', ''))[:300]}")
        text = payload.get(reply_field, "") or payload.get("result", "") or payload.get("response", "")
        new_session = payload.get("conversation_id", session_id) if adapter == "agy" \
            else payload.get("session_id", session_id)
    except RuntimeError:
        raise
    except Exception:
        # Plain-text fallback: treat stdout as the reply, keep the session.
        text = result.stdout.strip()
        new_session = session_id
    if not text:
        raise RuntimeError(f"{agent_name} returned an empty reply")
    return text, new_session


def write_reply(repo: Path, number: int, source_name: str, body: str,
                is_error: bool = False, agent_name: str = "") -> Path:
    out_dir = repo / "out"
    out_dir.mkdir(exist_ok=True)
    kind = "error" if is_error else "reply"
    path = out_dir / f"{number:03d}-{kind}.md"
    path.write_text(
        f"# {'Error on' if is_error else 'Reply to'} message {number:03d}\n"
        f"In reply to: in/{source_name}\n"
        + (f"Agent: {agent_name}\n" if agent_name else "")
        + f"At: {now_iso()}\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def process_one(repo: Path, config: dict, state: dict, state_path: Path,
                number: int, path: Path) -> None:
    started = state.setdefault("started", [])
    finished = state.setdefault("finished", [])
    if number in finished:
        return
    if number in started:
        # Started earlier but never finished: a previous run died mid-turn.
        # Do NOT run it again (could duplicate real work) - report the gap.
        log(f"#{number:03d} was started before but never finished; writing error reply")
        write_reply(repo, number, path.name,
                    "The bridge previously started this message but did not finish it "
                    "(crash, power loss, or the bridge was closed). It was NOT run again, "
                    "to avoid duplicating work. The human chair should review and, if safe, "
                    "send the message again under a new number.", is_error=True)
        finished.append(number)
        save_json(state_path, state)
        write_status(repo, "error", number, "started-but-unfinished; not re-run")
        git_push_out(repo, f"bridge: error reply for #{number:03d} (unfinished, not re-run)")
        return

    raw = path.read_text(encoding="utf-8").strip()
    max_chars = int(config.get("max_message_chars", 100_000))
    if len(raw) > max_chars:
        raise ValueError(f"message #{number:03d} is {len(raw)} chars, over the {max_chars} limit")
    default_agent = str(config.get("default_agent", "claude")).lower()
    agent_name, prompt = parse_addressee(raw, default_agent)

    started.append(number)
    save_json(state_path, state)  # record BEFORE running - the no-duplicates guarantee
    log(f"#{number:03d} -> {agent_name} is working")
    write_status(repo, "agent-working", number, f"{agent_name}: {path.name}")
    git_push_out(repo, f"bridge: {agent_name} working on #{number:03d}")

    sessions = state.setdefault("sessions", {})
    session_id = sessions.get(agent_name)
    if session_id is None and agent_name == "claude":
        session_id = state.get("session_id")  # legacy single-agent state
    try:
        reply, new_session = call_agent(config, agent_name, prompt, session_id)
        if new_session:
            sessions[agent_name] = new_session
            if agent_name == "claude":
                state["session_id"] = new_session
        write_reply(repo, number, path.name, reply, agent_name=agent_name)
        write_status(repo, "done", number, path.name)
        log(f"#{number:03d} -> reply written ({agent_name})")
    except Exception as exc:  # keep the meeting alive; report, don't crash
        write_reply(repo, number, path.name, f"The {agent_name} turn failed:\n\n{exc}",
                    is_error=True, agent_name=agent_name)
        write_status(repo, "error", number, str(exc)[:200])
        log(f"#{number:03d} -> ERROR ({agent_name}): {exc}")
    finished.append(number)
    save_json(state_path, state)
    git_push_out(repo, f"bridge: reply for #{number:03d}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Meeting Bridge (PC side)")
    parser.add_argument("--config", default=str(HERE / "bridge.config.json"),
                        help="path to bridge.config.json (default: next to bridge.py)")
    parser.add_argument("--once", action="store_true",
                        help="process at most one pending message, then exit")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser()
    if not config_path.exists():
        print(f"Config not found: {config_path}\n"
              f"Copy bridge.config.example.json to bridge.config.json and edit it first.",
              file=sys.stderr)
        return 2
    config = load_json(config_path, None)
    if not config or "project_dir" not in config:
        print(f"Config {config_path} must be JSON with at least \"project_dir\".", file=sys.stderr)
        return 2

    repo = Path(config.get("mailbox_dir", str(REPO_ROOT))).expanduser()
    if not repo.is_absolute():
        # A relative mailbox_dir is relative to THIS bridge folder, never to
        # the caller's working directory. (v0.3.1 fix: launched from the repo
        # root, ".." used to resolve to the repo's parent folder - no git
        # remote, no in/ - and the bridge idled silently forever.)
        repo = (HERE / repo).resolve()
    state_path = HERE / "bridge.state.json"
    state = load_json(state_path, {})

    lock_path = HERE / "bridge.lock"
    if lock_path.exists():
        print("Another bridge instance appears to be running (bridge.lock exists).\n"
              "If you are sure none is, delete bridge.lock and start again.", file=sys.stderr)
        return 3
    lock_path.write_text(str(os.getpid()), encoding="utf-8")

    poll = int(config.get("poll_seconds", 15))
    log(f"Bridge started. Mailbox: {repo} | project: {config['project_dir']} | poll: {poll}s")
    try:
        while True:
            git_sync_in(repo)
            pending = [(n, p) for n, p in list_messages(repo)
                       if n not in state.get("finished", [])]
            if pending:
                number, path = pending[0]  # strictly in order, one at a time
                process_one(repo, config, state, state_path, number, path)
                if args.once:
                    break
            elif args.once:
                log("No pending messages.")
                break
            else:
                time.sleep(poll)
    except KeyboardInterrupt:
        log("Bridge stopped by user.")
    finally:
        lock_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
