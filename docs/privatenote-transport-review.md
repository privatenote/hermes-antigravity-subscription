# Transport review: 2026-11-16

Reviewed the installed DirectSDK runtime modules (`__init__`, `client`, `prompt`,
`process`, `stream`, `models`, `delivery`, `debug`, `usage`) and their tests. Compared
the conversation and subprocess boundaries with the installed official experimental
Claude plugin and `neerazz/hermes-antigravity-oauth` at
`e4d0752d873ad4192b4630b0b0585b8c98ccc503`.

## The transports differ beyond the executable

Claude's `prepare_history` preserves native assistant/tool-use frames, tool-result
IDs and image blocks. Its request-scoped process and HTTP admission relay preserve
the current host tool inventory. It reads subprocess output through a queue.

Antigravity accepts a text payload assembled from the conversation, runs persistent
workers and translates text tool-call frames back to Hermes calls. Its historical
summary, tool-result and current-request boundaries therefore need explicit
representation. Changing only the executable does not preserve those semantics.

The other Antigravity plugin is derived from this transport. It adds workspace
`GEMINI.md` rules, live reasoning support and native-tool translation. Its prompt
builder still truncates historical results and flattens the message history. It
does not provide a ready replacement for compaction handoff handling. Its bounded
turn reader illustrates the appropriate deadline boundary; this fork implements
its own reader and additionally tests that it cannot read the next worker turn.

Sources:

- [Claude transport](https://github.com/NousResearch/hermes-plugin-claude-subscription-directsdk)
- [Other Antigravity prompt](https://github.com/neerazz/hermes-antigravity-oauth/blob/e4d0752d873ad4192b4630b0b0585b8c98ccc503/prompt.py)
- [Other Antigravity stream](https://github.com/neerazz/hermes-antigravity-oauth/blob/e4d0752d873ad4192b4630b0b0585b8c98ccc503/stream.py)

## Corrections

| Boundary | Failure | Correction |
| --- | --- | --- |
| Compaction | A reference summary became the active request and was copied into multiple objective sections | Extract only the unfinished request after the last summary end boundary; retain the summary once as reference |
| Skill state | Historical pruning markers competed with later full reloads | Identify complete successful loads by skill/file and result ID; preserve all original content and notices |
| Host notices | A notice appended after valid skill-result JSON hid the complete body from strict JSON decoding | Decode the leading JSON object while preserving the notice in the actual transcript |
| Pipe deadline | Blocking `readline()` could prevent the timeout loop from running | Read one turn through a bounded queue; stop at its result event |
| History identity | Shallow snapshots changed along with host edits; result IDs/names were omitted from comparison | Snapshot nested history independently and compare result identity |
| Tool inventory | A continuation could retain stale schemas or tool choice | Rebuild on changed tool contract; do not send a delta without a live or resumable conversation |
| Concurrent media | A oneshot needing new image permissions could retire another turn's worker | Only the owner of the worker lock may retire it; compare permission rules with rules, not raw paths |

## Verification and limits

- Complete suite: **496 passed, 75 subtests passed**.
- Real silent subprocess: deadline fires and terminates the process.
- Real Hydrogen xhigh, invented compaction/reload history: first emits
  `delegate_task`, then consumes a supplied invented review result and completes
  the rubric through the same native conversation. No repeated skill loads.
- Private incident evidence stays outside Git. Two authorized request-only replays
  compared the baseline with the initial compaction fix. Repeated calls fell from
  ten to two, but that intermediate fix did not complete the task. The final skill
  state logic was checked locally against those remaining repeated calls and
  recognizes their complete retained bodies, including appended host notices.

The live probe tests transport progress; its supplied review result is synthetic.
It does not establish end-to-end completion of the original private task. A native
CLI can still alter or limit the context it forwards; a successful local prompt
assembly alone cannot prove every token reached the model. Keep Hermes' loop
guardrails enabled.
