# Agent Meeting Bridge

**Let your AI agents talk to each other — in a meeting you chair, instead of you copy-pasting between them.**

You have one AI agent on your phone / in the cloud (the planner, the one you chat with) and another agent on your computer (the worker, the one with your files and tools). Today, *you* are the bridge: you copy a reply from one, paste it into the other, copy the answer back, and hope the threads don't cross on something time-sensitive.

This repo replaces you-the-copier with a simple, ordered mailbox:

```
        You — chair the meeting, watch, interject or stop anytime
                          │
        Chair agent (e.g. Muse)  ── sends numbered message #1, #2, #3…
                          ▼
        Private mailbox repo (this repo, your private copy)
            in/   messages to the worker agent
            out/  the worker agent's replies
            status.json   idle | agent-working | done | error
                          ▲
                          │  polled every ~15 seconds by:
        Bridge (small Python program on your computer)
                          │  runs one turn per message:
                          ▼
        Worker agent (v1: Claude Code, headless)
            claude -p "<message>" --resume <meeting-session>
```

No session needs to be "awake" to receive a message — the bridge *starts* the worker agent for each turn, and `--resume` carries the conversation. Turns are numbered and strictly one at a time, so nothing crosses and nothing runs twice. Every message and reply is a committed file: you get a full meeting transcript for free.

**Multi-way meetings:** the bridge can seat more than one worker agent. Address a message with a `To:` line and it goes to that agent, each with its own session:

```
python tools/send_message.py --to claude "Draft the fix and explain it."
python tools/send_message.py --to gemini "Review Claude's draft above: <paste>. What did he miss?"
```

With a human chairing, a chair agent, Claude Code and Gemini in the room, that's a four-way meeting — second opinions and cross-checks included, with the human watching instead of relaying.

> **Which CLI serves the Gemini seat?** Since 18 June 2026, Gemini CLI no longer serves individual, free, or Google AI Pro/Ultra accounts — Google moved those users to the **Antigravity CLI (`agy`)**. So for most people the Gemini seat is configured as `"adapter": "agy", "command": "agy"` (the example config does exactly this; `agy` speaks the same headless shape, resuming via `--conversation <id>`). If you have an enterprise Gemini Code Assist licence or a paid Gemini API key, Gemini CLI still works — set the seat to `"adapter": "gemini", "command": "gemini"` instead. Either way the seat is still addressed as `To: gemini`; only the engine behind it changes.

## Who this is for

Anyone who runs AI agents and relays between them by hand. Version 1 links **Muse ↔ Claude Code**, and seats **Gemini CLI** as an additional participant in the same meeting. The mailbox protocol (see [PROTOCOL.md](PROTOCOL.md)) is deliberately agent-agnostic — an adapter for another agent is just "a command that takes a prompt and returns a reply + a session id".

## Two repos, not one

- **This template repo is public and contains no private data** — just the bridge, the protocol, and the skills. Use it as a GitHub template.
- **Your meeting repo must be a private copy.** Your conversations live in it. Never hold a meeting in a public repo.

## Setup (about 10 minutes)

You need: Python 3.10+, Git, and Claude Code installed and signed in on the computer that will run the bridge.

1. Click **Use this template → Create a new repository**, set it to **Private**, and clone your new repo onto your computer.
2. Copy `bridge/bridge.config.example.json` to `bridge/bridge.config.json` and set:
   - `project_dir` — the default folder worker agents work in (its files, its context). A seat in the `agents` table can name its own `project_dir` to work in a different project — see "Several projects, one bridge" below.
   - `agent_command` — normally just `claude`.
   - `mailbox_dir` — leave as `..` (the repo root, where `bridge/` lives).
3. Give your chair agent access to the same private repo (e.g. Muse with GitHub access), and point it at the chair skill in `skills/chair/SKILL.md`.
4. Start the meeting on your computer: double-click `start-meeting.bat` (Windows) or run `./start-meeting.sh` (macOS/Linux). Leave it running while you meet.
5. Ask your chair agent to send the first message — or send one yourself:

   ```
   python tools/send_message.py "Hello — please confirm you can read this project, and summarise what it contains. Discussion only, change nothing."
   ```

6. Watch `status.json` flip to `agent-working`, then read the reply in `out/`. The chair agent can now continue the conversation turn by turn, in front of you.

## Several projects, one bridge

One bridge can serve several projects at once. Each project gets its **own worker seat**: an entry in the config's `agents` table with its own `project_dir`, for example a `claude` seat for one project and a `claude-other-project` seat for another (the example config shows the shape). A seat without its own `project_dir` uses the top-level one. You address a seat by name — `To: claude-other-project` — and each seat keeps its own session and works only in its own folder.

A worker inherits a project from **files, never from another session's memory** — it cannot see what an interactive session on the same project knows. So each project folder should carry a `PROJECT-CONTEXT.md`: a short handover brief (what the project is, how the work flows, the standing rules, where things stand, what is open, what must not break), kept current by whoever works the project day to day. On a seat's first turn, the bridge automatically points the worker at that file before anything else.

## Safety model

- **The human chairs.** The chair agent must show the human any *new work* instruction and get a go-ahead before sending it, unless the human pre-approved the meeting's scope ("discuss and decide X between you"). Discussion is free; work is gated.
- **One writer, one turn.** Only the bridge writes `out/` and `status.json`; only the chair side writes `in/`. Numbers are never reused.
- **No duplicate runs.** The bridge records a message as started *before* running it. If the bridge dies mid-turn, that number gets an error reply — it is never silently run again.
- **Private by default.** Your real config (`bridge.config.json`), bridge state, and your whole meeting repo stay private and are git-ignored where they should be.

## Honest limits (v1)

- The meeting is with a **dedicated meeting session** of the worker agent in your project folder — not a barge-in on an interactive session that is mid-run. (Interrupting a running turn is how threads cross; that's the problem this design exists to avoid.) You can resume the meeting session interactively yourself afterwards with `claude --resume <session-id>`.
- Turn-by-turn, not real-time: a message waits until the current turn finishes. That's normal meeting behaviour.
- Your computer must be on and the bridge running during a meeting.
- Worker turns bill to *your* agent plan exactly as if you typed them. The bridge and repos are free.

## Layout

| Path | What it is |
|---|---|
| `bridge/bridge.py` | The PC-side bridge (standard library only) |
| `bridge/bridge.config.example.json` | Config template — copy to `bridge.config.json` |
| `tools/send_message.py` | Chair-side helper: writes the next numbered message and pushes it |
| `in/`, `out/` | The mailbox: numbered messages and replies |
| `status.json` | Live meeting state |
| `skills/chair/SKILL.md` | Instructions for the chair agent |
| `skills/worker/SKILL.md` | Instructions/context for the worker agent side |
| `PROTOCOL.md` | The mailbox protocol, written for humans and future adapters |
| `templates/message-template.md` | A well-formed meeting message |

## Roadmap

- **Phase 2:** push messages into a *live interactive* worker session via a custom channel, once the mailbox flow is proven. The mailbox and protocol stay the same; only the last hop changes.

## License

MIT — see [LICENSE](LICENSE). Built so anyone can install it and link their own agents.
