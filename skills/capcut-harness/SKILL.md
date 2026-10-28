---
name: capcut-harness
description: Run the local CapCut browser workspace and reversible dialogue loudness jobs, with measured A/B review, exclusions, Apply and Undo. Use for balancing speech across a readable local CapCut project or inspecting saved harness jobs.
---

# CapCut Harness

Use the installed launcher `~/.local/bin/capcut-harness` (Windows: `capcut-harness.py`) or its path from `~/.local/share/capcut-harness-tool/.installation.json`. Source checkout: `python -m capcut_harness`. `--help` lists options. Launch the local browser UI; no Computer Use is needed. Default state: `~/.local/share/capcut-harness`; keep it for backups and Undo.

If absent, install the pinned release using the repository's `install-harness.py`; Python 3.10–3.13 and FFmpeg/ffprobe are prerequisites. Prepare missing dependencies through the terminal within the user's request; don't ask them to edit files. An unmanaged directory is preserved; choose a separate managed install location rather than deleting it.

## Workflow

- Confirm the intended project; discover from default CapCut roots or pass `--project-root PATH`. `inspect PATH` returns actual metadata. Inspecting does not write the project.
- `command "cân âm thoại PROJECT"` uses the same job registry as the UI and waits for completion. With the UI running, commands connect to that service. This is a finite grammar, not a shell or another LLM. Commands include `phân tích PROJECT`, `áp dụng JOB`, `hoàn tác JOB`, `thử lại JOB`.
- Review the actual report: accepted/excluded intervals, before/after P10–P90 spread, target attainment, true peak, sample count and unsupported-source findings. The UI seeks intervals and switches synchronized A/B. Change target/boost/ceiling or exclusions there, then update the listening revision. Exclusions set gain to zero; the final peak limiter still covers the complete master.
- Defaults: speech target −18 LUFS, maximum boost/cut 12 dB, whole-master ceiling −1.5 dBTP, stereo 48 kHz PCM24 WAV. VAD identifies voice activity; it does not identify speakers, transcribe, remove music or separate stems. Music under speech changes with that speech interval. Singing/short/noisy speech can be misclassified; let the user inspect/exclude it. Report target deviations separately from quality flags: VAD scores are heuristic, near-full-scale source samples are not proof of clipping, and measured 20 ms RMS attenuation after limiting is not the limiter’s internal gain. Singing/music-vocal classification stays unassessed. Never promise every source hits target.
- Analysis/render writes only job outputs. Apply requires saved and closed CapCut and a current review revision; it adds one root audio master and mutes audible original root segments. Nested compound, video and card structures are preserved. Respect existing authorization for Apply; otherwise present the concrete A/B result for review. Never kill CapCut or bypass stale/unsupported guards.
- Undo restores exact saved draft mirrors only while known hashes match. After restart use Retry to recover interrupted work; mutation retries reuse the staged transaction. Do not delete state or manually overwrite changed drafts. Foreign edits stop restoration and are preserved.

Initial compatibility evidence is macOS and readable unencrypted schema 360000. Unsupported audible effects/routing, unknown mute flags, reverse or variable speed are refused. `editor_render_verified: false` means only file-level preservation and reconstructed audio have been checked. Do not claim native CapCut playback/export verification without actually hearing/rendering that result.

## Cards

Use the sibling `$capcut-cinematic-cards` skill for necessary time/location cards and first-appearance character names **with short verified roles**, styled for the film. That workflow checks scene/dialogue evidence, prefers quiet dark transitions, and adds separate root text tracks. The harness Cards view lists existing text; it does not automatically identify characters or invent cinematic placement.
