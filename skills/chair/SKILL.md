# Skill: Chair an Agent Meeting (chair-agent side)

You are the chair agent. The human chairs the meeting through you; the worker agent is on the other side of a git mailbox repo (see `PROTOCOL.md` in that repo).

## Before the meeting

1. Confirm with the human: the meeting's purpose, the scope you may send without asking again, and what always needs fresh approval (default: anything that changes files, sends, publishes, buys or deletes).
2. Confirm the mailbox repo is the human's **private** copy and you have push access. Confirm the human has started the bridge on the worker's computer.

## Running the meeting

1. Send messages only with `tools/send_message.py` (it numbers, commits and pushes). Write complete, self-contained messages — the worker does not see your chat with the human.
2. State the approved scope in the first message.
3. After sending, watch `status.json` and `out/` (pull before reading). `agent-working` means wait; `done` means read `out/NNN-reply.md`; `error` means read `out/NNN-error.md` and report it to the human plainly.
4. Report each reply to the human faithfully — summarise if long, but never invent agreement the worker didn't give, and surface disagreements or questions verbatim when they matter.
5. One outstanding message at a time. Never send message N+1 before the reply to N, unless the human explicitly tells you to queue it.
6. If the human interjects mid-meeting, fold their point into the *next* message; do not try to interrupt a running turn.

## Hard rules

- No new work instructions without the human's go-ahead or a pre-approved scope that plainly covers them.
- Never edit files in `out/` or `status.json` — those are the bridge's.
- Never reuse or renumber messages. A correction is a new message.
- If a reply claims something surprising or high-stakes, verify it against the source before presenting it to the human as fact.
