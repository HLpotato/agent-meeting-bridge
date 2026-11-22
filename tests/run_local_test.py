#!/usr/bin/env python3
"""End-to-end local test of the meeting bridge - no network, no real agent.

Copies the template into a temp folder, inits git, points the bridge at the
fake agent, sends message #1, runs the bridge, and checks:
  - out/001-reply.md exists and contains the fake reply
  - status.json says done for message 1
  - a second bridge run does NOT re-run message 1 (no duplicate turns)
  - message #2 resumes the same session

Run:  python3 tests/run_local_test.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent


def run(cmd, cwd, check=True):
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"FAILED: {' '.join(map(str, cmd))}\n{result.stdout}\n{result.stderr}")
        sys.exit(1)
    return result


def main():
    tmp = Path(tempfile.mkdtemp(prefix="meeting-bridge-test-"))
    box = tmp / "mailbox"
    shutil.copytree(TEMPLATE, box, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "bridge.config.json", "bridge.state.json",
        "bridge.lock", "calls.log"))
    project = tmp / "project"
    project.mkdir()
    (project / "hello.txt").write_text("test project\n", encoding="utf-8")
    # The main project carries a handover brief; the second project (below)
    # deliberately does not, so both branches of the first-turn rule run.
    (project / "PROJECT-CONTEXT.md").write_text(
        "# Project context\nThe handover brief for this project.\n", encoding="utf-8")
    project2 = tmp / "project2"
    project2.mkdir()
    (project2 / "other.txt").write_text("second project\n", encoding="utf-8")

    run(["git", "init", "-q"], box)
    run(["git", "config", "user.email", "test@example.com"], box)
    run(["git", "config", "user.name", "Bridge Test"], box)
    run(["git", "add", "-A"], box)
    run(["git", "commit", "-qm", "template"], box)

    # The fakes are invoked as: <shim> -p "<prompt>" ... so each agent's
    # command is a shim script that runs the right fake with this python.
    def make_shim(name, fake_file):
        shim = tmp / name
        shim.write_text(
            "#!/usr/bin/env python3\n"
            "import subprocess, sys\n"
            f"sys.exit(subprocess.run([sys.executable, {str(box / 'tests' / fake_file)!r}] + sys.argv[1:]).returncode)\n",
            encoding="utf-8")
        shim.chmod(0o755)
        return str(shim)

    config = {
        "project_dir": str(project),
        "mailbox_dir": str(box),
        "poll_seconds": 1,
        "default_agent": "claude",
        "agents": {
            "claude": {"command": make_shim("fake-claude-shim.py", "fake_agent.py"),
                       "adapter": "claude"},
            "gemini": {"command": make_shim("fake-gemini-shim.py", "fake_gemini.py"),
                       "adapter": "gemini"},
            "agy": {"command": make_shim("fake-agy-shim.py", "fake_agy.py"),
                    "adapter": "agy"},
            # A second Claude seat pinned to its own project folder (v0.4
            # multi-project): same adapter, different desk.
            "claude2": {"command": make_shim("fake-claude2-shim.py", "fake_agent.py"),
                        "adapter": "claude", "project_dir": str(project2)},
        },
    }
    (box / "bridge" / "bridge.config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    # Send message 1 (locally - no remote to push to)
    run([sys.executable, "tools/send_message.py", "--no-push",
         "Hello worker, this is test message one."], box)

    # Run the bridge once
    run([sys.executable, "bridge/bridge.py", "--once"], box)

    reply = box / "out" / "001-reply.md"
    assert reply.exists(), "out/001-reply.md was not created"
    body = reply.read_text(encoding="utf-8")
    assert "test message one" in body, f"reply does not echo the prompt:\n{body}"
    status = json.loads((box / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "done" and status["message"] == 1, f"bad status: {status}"

    calls = (box / "tests" / "calls.log").read_text(encoding="utf-8").strip().splitlines()
    assert len(calls) == 1, f"agent should have run exactly once, ran {len(calls)}"

    # Run again with nothing new: no duplicate turn
    run([sys.executable, "bridge/bridge.py", "--once"], box)
    calls = (box / "tests" / "calls.log").read_text(encoding="utf-8").strip().splitlines()
    assert len(calls) == 1, "message 1 was run twice - duplicates bug!"

    # Message 2 resumes the session
    run([sys.executable, "tools/send_message.py", "--no-push",
         "Second message, please continue."], box)
    run([sys.executable, "bridge/bridge.py", "--once"], box)
    reply2 = (box / "out" / "002-reply.md").read_text(encoding="utf-8")
    assert "resumed=True" in reply2, f"message 2 did not resume the session:\n{reply2}"

    # Message 3 is addressed to Gemini: routed to the Gemini adapter, the
    # routing line is stripped, and Gemini's own session is separate.
    run([sys.executable, "tools/send_message.py", "--no-push", "--to", "gemini",
         "Gemini, please review the plan."], box)
    run([sys.executable, "bridge/bridge.py", "--once"], box)
    reply3 = (box / "out" / "003-reply.md").read_text(encoding="utf-8")
    assert "Fake Gemini reply" in reply3, f"message 3 was not answered by Gemini:\n{reply3}"
    assert "Agent: gemini" in reply3, f"reply 3 does not record the agent:\n{reply3}"
    assert "To: gemini" not in reply3, f"routing line leaked into the prompt:\n{reply3}"
    calls = [json.loads(line) for line in
             (box / "tests" / "calls.log").read_text(encoding="utf-8").strip().splitlines()]
    gemini_calls = [c for c in calls if c.get("agent") == "gemini"]
    claude_calls = [c for c in calls if c.get("agent") == "claude"]
    assert len(gemini_calls) == 1 and len(claude_calls) == 2, f"bad routing: {calls}"
    assert gemini_calls[0]["resumed"] is False, "Gemini must start its own fresh session"

    # Message 4 goes to the agy adapter (Antigravity CLI - the Gemini seat for
    # individual accounts): routed via --conversation, not --resume.
    run([sys.executable, "tools/send_message.py", "--no-push", "--to", "agy",
         "agy, second opinion please."], box)
    run([sys.executable, "bridge/bridge.py", "--once"], box)
    reply4 = (box / "out" / "004-reply.md").read_text(encoding="utf-8")
    assert "Fake agy reply" in reply4, f"message 4 was not answered by agy:\n{reply4}"
    calls = [json.loads(line) for line in
             (box / "tests" / "calls.log").read_text(encoding="utf-8").strip().splitlines()]
    agy_calls = [c for c in calls if c.get("agent") == "agy"]
    assert len(agy_calls) == 1 and agy_calls[0]["resumed"] is False, f"bad agy routing: {calls}"

    # Message 5 to agy again resumes via the stored conversation_id.
    run([sys.executable, "tools/send_message.py", "--no-push", "--to", "agy",
         "agy, follow up."], box)
    run([sys.executable, "bridge/bridge.py", "--once"], box)
    reply5 = (box / "out" / "005-reply.md").read_text(encoding="utf-8")
    assert "resumed=True" in reply5, f"message 5 did not resume the agy conversation:\n{reply5}"

    # PROJECT-CONTEXT first-read (v0.4): the main project's brief is pointed
    # out on the Claude seat's FIRST turn only - message 1 carries the
    # read-first line, the resumed message 2 does not.
    calls = [json.loads(line) for line in
             (box / "tests" / "calls.log").read_text(encoding="utf-8").strip().splitlines()]
    main_seat = [c for c in calls if c.get("cwd") == str(project)]
    assert len(main_seat) == 2, f"main seat should have run twice: {calls}"
    assert "PROJECT-CONTEXT.md" in main_seat[0]["prompt"], \
        f"first turn did not point at the brief:\n{main_seat[0]['prompt']}"
    assert "PROJECT-CONTEXT.md" not in main_seat[1]["prompt"], \
        "brief line must be prepended on the first turn only"

    # Message 6 to the second Claude seat: it runs in ITS OWN project
    # folder, keeps its own session, and - that folder has no brief - gets
    # no read-first line.
    run([sys.executable, "tools/send_message.py", "--no-push", "--to", "claude2",
         "Second project worker, checking in."], box)
    run([sys.executable, "bridge/bridge.py", "--once"], box)
    reply6 = (box / "out" / "006-reply.md").read_text(encoding="utf-8")
    assert "Agent: claude2" in reply6, f"reply 6 does not record its seat:\n{reply6}"
    calls = [json.loads(line) for line in
             (box / "tests" / "calls.log").read_text(encoding="utf-8").strip().splitlines()]
    seat2 = [c for c in calls if c.get("cwd") == str(project2)]
    assert len(seat2) == 1, f"second seat should have run once, in its own folder: {calls}"
    assert seat2[0]["resumed"] is False, "second seat must start its own fresh session"
    assert "PROJECT-CONTEXT.md" not in seat2[0]["prompt"], \
        "no brief in the folder means no read-first line"

    print("ALL TESTS PASSED")
    print(f"(test mailbox kept at {box})")


if __name__ == "__main__":
    main()
