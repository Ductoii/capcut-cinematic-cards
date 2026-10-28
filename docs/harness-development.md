# Developer guide

Python 3.10–3.13, FFmpeg/ffprobe, pinned NumPy/ONNX Runtime. Build with `python -m pip wheel . --no-deps`. The wheel includes card helpers, Silero model/license, web assets/font/license and `capcut-harness-mcp`. The managed installer also registers the Codex plugin; a plain pip install does not register it.

## Components

- `mcp.py`: stdio MCP tools, inline MCP App resource, loopback service startup. `capcut_open_workspace` has the thread entrypoint; no second model/native IPC bypass.
- `web/host.js`: MCP Apps JSON-RPC host initialization, tool calls and `ui/message` follow-ups. Host rejection/timeout remains visible.
- `workspace.py`: durable request UUIDs, input hashes, chat/connection binding and ordered result events. Completed UUIDs are not rerun.
- `server.py`: authenticated loopback API; component API calls use MCP tools, audio uses random read-only per-job media capabilities. No broad cross-origin mutation API.
- `source_audio.py`: source-local conditioned VAD, weighted take anchor, bounded phrase trims, gentle RMS compressor, source and master peak protection. Separate sources are processed before summation.
- `audio.py`: shared parameters/envelopes; legacy engine retained for old saved jobs.
- `service.py`, `jobs.py`: serialized persisted jobs, cancellation and source/revision ownership.
- `transaction.py`: external master, guarded Apply/Undo. Existing card helper uses its own stage/apply/restore guards.
- `skills/capcut-harness`: canonical skill plus card scripts and conditional references; wheel packages scripts as `cards_backend`.

## Development entrypoints

`python -m capcut_harness.mcp` starts the MCP transport. `python -m capcut_harness --no-browser --state-dir /tmp/own-state --project-root /path/to/projects` starts standalone diagnostics. Its legacy finite CLI parser is not the panel's freeform interface.

The managed installer writes a local marketplace, registers it with `codex plugin marketplace add`, then installs with `codex plugin add`. Runtime interpreter paths are absolute; a fresh chat may be required for tool discovery. No user config editing or replacement model/session.

The UI bridge requires actual host support. Do not infer successful rendering/delivery from a valid MCP JSON response. Do not label source reconstruction as native editor verification.

## Delivery evidence

For v0.3.0 the owner explicitly declined additional review/recheck, a 300-source exercise and another full-film run. Delivery is limited to necessary syntax, packaging and installation checks; historical tests are retained for developers but are not claims about this release's audio quality. No media fixtures or personal projects are published.
