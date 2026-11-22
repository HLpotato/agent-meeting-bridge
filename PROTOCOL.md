# The Mailbox Protocol

A deliberately boring protocol. Boring is what keeps two AI agents and one human from talking over each other.

## Roles

- **Chair (human):** owns the meeting. Approves the scope, can interject or stop at any time, approves any instruction that causes real work.
- **Chair agent:** runs the conversation from the human's side. Writes messages to `in/`, reads replies from `out/`, reports to the human.
- **Bridge:** a dumb, trustworthy courier on the worker's computer. Polls the mailbox, runs one worker turn per message, writes replies. It has no opinions and makes no decisions.
- **Worker agent:** does the discussing/working on its own computer, in its project folder. Replies once per message.
- **More worker agents (multi-way meetings):** a meeting can seat several worker agents (v1 adapters: Claude Code and Gemini CLI). Each message is addressed to exactly one agent with a `To: <name>` first line (no line = the default agent). Each agent keeps its *own* session and its own context; the chair agent relays between them when their views need to meet — e.g. "Claude proposed X; Gemini, review it" — pasting the relevant text into the next message, because agents do not see each other's replies directly. The reply file records which agent answered (`Agent:` header).
- **One seat per project (multi-project meetings):** a seat may name its own `project_dir` in the bridge config, so one bridge can seat workers for several projects at once — each seat working only in its own project's folder, with its own session. A worker learns its project from files, never from another session's memory; each project folder should carry a `PROJECT-CONTEXT.md` handover brief, and on a seat's first turn the bridge points the worker at that file automatically.

## Files

- `in/NNN-<slug>.md` — one message from the chair side. `NNN` is zero-padded, strictly increasing, never reused.
- `out/NNN-reply.md` — the worker's reply to message `NNN`. `out/NNN-error.md` — the turn failed or could not be completed; the body explains why.
- `status.json` — `{"state": "idle" | "agent-working" | "done" | "error", "message": NNN | null, "detail": "...", "updated_at": "<iso8601>"}`

## Rules

1. **One turn at a time.** The bridge processes the lowest unfinished number first and never starts a turn while another is running.
2. **Single writer.** Only the chair side writes `in/`; only the bridge writes `out/` and `status.json`. Nobody edits another role's files.
3. **Record before running.** The bridge marks a number as started (in its local `bridge.state.json`) *before* invoking the worker. A started-but-unfinished number is never re-run automatically; it receives an `out/NNN-error.md` explaining the gap, and the chair decides what to do. This trades "possibly lost turn" for "never duplicated work" — the right trade when turns can change files or spend money.
4. **One conversation.** All turns in a meeting share one worker session (the bridge resumes it by session id). Starting a new meeting = clearing the bridge state and, if desired, archiving the transcript.
5. **Approval gate.** Discussion, questions and read-only checks are free. Any message that instructs the worker to change, build, send, publish, buy or delete something must be approved by the human chair first — either message-by-message, or by a scope the human approved at the meeting's start. The chair agent states the scope in the first message of the meeting.
6. **Plain text, full context.** Messages are complete and self-contained (the worker may not have the chair's chat history). Quote what matters; don't write "as discussed above" about things said outside the mailbox.
7. **Transcript is the record.** Because every turn is a committed file, the repo history *is* the meeting minutes. Don't rewrite history files; correct mistakes with a new message.

## Writing an adapter for another worker agent

An adapter needs exactly one operation:

```
run_turn(prompt, session_id | None) -> (reply_text, new_session_id)
```

- v1 (Claude Code): `claude -p "<prompt>" --output-format json [--resume <session_id>]`, reading `result` and `session_id` from the JSON.
- Gemini CLI: `gemini -p "<prompt>" --output-format json [--resume <session_id>]`, reading `response` and `session_id` from the JSON. Same shape, different field name for the reply. (Enterprise Code Assist licences and paid Gemini API keys only since 18 Jun 2026.)
- Antigravity CLI (`agy`, Google's successor for individuals): `agy -p "<prompt>" --output-format json [--conversation <conversation_id>]`, reading `response`, `status` and `conversation_id` from the JSON envelope. Same shape again; the resume flag and the session field have different names.
- Anything with a headless/CLI mode, an SDK, or an API can implement the same operation. The mailbox, numbering, status and safety rules do not change.

## Message format

See `templates/message-template.md`. In short: state the scope/approval line, then the ask, then what a good reply looks like (answer only vs. propose vs. do).
