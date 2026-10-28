---
name: capcut-harness
description: Open the local CapCut editing panel beside this Codex chat, receive freeform UI requests, add cinematic time/location/character cards and balance dialogue across source clips. No Computer Use or second model.
---

# CapCut Harness

One skill owns the workspace, cinematic cards and dialogue. Work through local tools and files; no Computer Use, separate API key or second model.

## Start the workspace

Call `capcut_open_workspace`. Its MCP App opens in the conversation panel and sends natural-language requests through the hosting chat's `ui/message` bridge. Do not substitute the standalone HTTP browser and claim it can send messages to Codex. If the tool is missing, inspect `~/.local/share/capcut-harness-tool/.installation.json` and the installed plugin status; run the managed installer's registration repair as needed. Prepare dependencies yourself. Never ask the user to edit JSON/configuration. A newly registered local MCP server may require a fresh chat before tools appear; disclose that actual limitation rather than spawning another model or duplicating the chat.

Use the installed `~/.local/bin/capcut-harness` for project inspection/diagnostics, and the registered private Python runtime for the plugin transport. Preserve `~/.local/share/capcut-harness`: it holds listening masters, request results and exact Undo backups.

## Receive requests from the panel

Messages labeled `[CapCut Harness request UUID]` are the user's freeform requests in this same chat, not a fixed command language. Call `capcut_request_get` with that UUID to read authoritative text, selected project and structured context. If complete/cancelled, do not repeat it. Otherwise publish `acknowledged` through `capcut_request_update`, do the requested work with normal tools, and publish concise `working` and terminal `complete`/`blocked`/`failed` updates. Include `job_id` or `stage_id` when available. Resolve uncertainty from the project context before asking. The backend's registry is a tool interface, never a restriction on what the user may ask Codex.

Use the request's `connection_id` with `capcut_workspace_data` and `capcut_action`. `capcut_action` takes a structured `action` object. Job work is asynchronous: read `/api/jobs/JOB_ID` until terminal; do not call Apply before preparation has completed. Do not claim completion from a queued ticket. Publish the actual outcome to the request panel.

## Choose the workflow

- **Cinematic cards:** read [cards](references/cards.md), [editing](references/editing.md) and [tool/plan](references/tool.md). This skill's `scripts/cards.py` is the canonical helper. Choose necessary time/location changes, first visible character appearances with verified short roles, and film-specific typography. Review the whole hold; protect dialogue and important shots. Add separate editable root text tracks; preserve original fades and compounds. Stage completely before editor-close coordination, then apply/verify or restore using the existing guards.
- **Dialogue:** read [dialogue](references/dialogue.md). Use `dialogue.analyze` with the selected project. The online-film preset levels each source's speech before summation, gently compresses protruding syllables, and protects peaks. Publish the resulting listening job. Do not run an extra whole-film verification/listening cycle unless requested; respect the user's chosen workflow. Never claim studio mastering, universal YouTube certification or restoration of already distorted audio.
- **Other editing requests:** interpret the user's intent naturally. Use available capabilities where suitable; explain a concrete missing capability without returning a regex “unsupported command” error. Do not expand a request into unrelated edits.

## Writes and recovery

Analysis/listening output does not change the project. Apply requires saved/closed CapCut and current source/revision hashes. Respect the user's authorization; never kill CapCut or bypass freshness checks. Dialogue adds an external master and mutes only known original root audio participants; nested compounds, picture, text and timing stay intact. Card writes add owned text only. Undo/restore stops on later foreign edits and preserves them. File-level preservation and source-reconstructed audio are not proof of native CapCut playback/export.
