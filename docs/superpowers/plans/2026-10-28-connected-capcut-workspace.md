# Connected CapCut Workspace Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. User explicitly requested direct implementation without approval/recheck cycles; those lower-priority skill gates do not apply.

**Goal:** One local skill/plugin opens a same-chat editing panel and balances disparate source dialogue for online films.
**Architecture:** Reuse the Python local service and guarded draft writers. Add source-first speech processing and a stdio MCP App protocol adapter; the host sends freeform UI messages to its current chat.
**Tech Stack:** Python, NumPy/ONNX Runtime, FFmpeg, vanilla HTML/CSS/JS, local MCP plugin.
**Spec:** docs/superpowers/specs/2026-10-28-connected-capcut-workspace-design.md

## Global Constraints
- No Computer Use, second model/API key, media upload, modification of compound contents or real-project Apply.
- Keep persisted v0.2.0 jobs and exact Undo readable.
- User rejected approval and verification cycles: no 300-source workload, whole-film reanalysis or independent review. Build/package only as necessary.

## Review Focus
- Very quiet dialogue must be detected using analysis-only conditioning.
- Speech correction happens per source so an independent music bed does not pump.
- Source-instance identity includes ancestry; overlapping sources stay distinct.
- UI messages are host routed to their containing chat; HTTP-only launch cannot imply connection.
- Existing job paths, backups and restoration guards survive install migration.

### Task 1: Source-aware online-film dialogue
Files: source_audio.py (new), mix.py, speech.py, audio.py, service.py.
Interface: analyze_sources(inventory, out, params, progress, cancelled) returns existing analysis fields plus source rows and per-source artifacts. render_sources(analysis, out, params, excluded, progress, cancelled) returns the existing master/report contract with source coverage.
- [ ] Preserve mapped source instances during decoding; detect quiet speech on a conditioned analysis copy.
- [ ] Speech-anchor each source, apply gentle phrase leveling/dynamics and sum corrected sources before final peak protection. Default speech −16 LUFS, ceiling −1.5 dBTP, explicit 48 dB correction budget.
- [ ] Keep exclusions and legacy report rendering working; export source coverage and measured misses without hiding no-speech clips.

### Task 2: Same-chat MCP App and request lifecycle
Files: mcp.py and workspace.py (new), server.py, __main__.py, web/app.js/index.html/style.css.
Interface: workspace.open/state/submit/update plus action/tool calls; UI resource and thread entrypoint metadata; request UUID and persisted event sequence.
- [ ] Add stdio MCP tools/resources, separated rendering/data calls and durable request state.
- [ ] Bundle the local UI resource with host bridge initialization; use ui/message for arbitrary user requests and tools/call for state/actions.
- [ ] Publish agent acknowledgment/progress/result and provide scoped loopback audio playback. Disconnected browser mode remains honest.

### Task 3: One self-contained skill and install
Files: skills/capcut-harness, canonical card backend path, install-harness.py, plugin manifests, pyproject.toml.
- [ ] Fold card scripts/evidence/style workflow beneath capcut-harness; retain standalone compatibility without a sibling dependency.
- [ ] Register the local plugin automatically with one primary skill, local stdio server and conversation panel. Preserve unrelated configuration and installed data.
- [ ] Update Vietnamese/English README, UI copy and release version.

### Task 4: Package and deliver
- [ ] Build runnable package and update managed local installation without whole-film reanalysis.
- [ ] Commit/publish to the already-authorized public repository and update one-line install.
- [ ] Open the installed workspace using available host capabilities; accurately state any unverified native behavior.
