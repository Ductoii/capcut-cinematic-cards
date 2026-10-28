# CapCut Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local browser workspace that runs reversible CapCut jobs and levels dialogue across a complete project, with measured A/B review.

**Architecture:** Python package `capcut_harness` serves bundled vanilla HTML/CSS/JS on loopback and owns a persisted, single-worker job queue. A strict timeline adapter reconstructs supported audio into a float mix, local VAD identifies speech, phrase loudness drives a smooth bounded gain envelope, and a verified PCM master is applied as one root track. Existing cinematic-card CLI is retained and adapted through the same registry/lock.

**Tech Stack:** Python 3.10+, stdlib HTTP/JSON/threading/subprocess, NumPy, ONNX Runtime, bundled licensed Silero VAD model, FFmpeg/ffprobe. Vanilla JS/CSS, local Inter font. Headless Chromium for browser verification; no Computer Use.

**Spec:** `docs/superpowers/specs/2026-10-28-capcut-harness-design.md`, approved by user 2026-10-28.

## Global Constraints

- Initial validated platform: macOS; readable unencrypted CapCut JSON schema 360000 only.
- No computer use, no moving/retiming shots or replacing original media, no nested-compound or card changes.
- Audio defaults: dialogue -18 LUFS, maximum boost 12 dB, final ceiling -1.5 dBTP; stereo 48 kHz PCM 24-bit WAV.
- Loopback only, session/Host/Origin checks, no shell execution from commands, no arbitrary file-serving endpoint.
- Use existing `.capcut-cards.lock`, exact mirror backups/CAS, application-closed guard, journaled recovery and guarded undo.
- No success claim for native CapCut rendering without native evidence; keep `editor_render_verified: false`.
- Publish no private film assets, paths, generated masters, or test recordings.

## Review Focus

- Detached audio and embedded audio sharing a source may have native mute controls beyond `volume`; the mix must not double dialogue.
- An application saving between staging and apply, or reopening midway, must preserve foreign edits and leave recoverable state.
- A long film must not allocate a duration-sized gain matrix or run unbounded concurrent FFmpeg processes.
- Retried requests, restart, exclusion changes and repeated normalization must not apply stale revisions or feed output back into itself.
- Low speech confidence, music vocals, clipped sources and peak limiting must appear as measured exceptions rather than promised target attainment.

### Task 1: Strict audio inventory and reconstruction

**Files:** `capcut_harness/__init__.py`, `legacy.py`, `process.py`, `timeline.py`, `mix.py`; `tests/test_harness_mix.py`.

**Interfaces:** `legacy.cards` exposes the existing helper module. `timeline.inspect_audio(project: Path) -> dict` returns project/hash/mirrors/duration/sources/issues and root mute IDs; source records carry affine bounds, source offset, speed, gain and ancestor/segment fade envelopes. `mix.render_mix(inventory: dict, out: Path, progress: callable, cancelled: callable) -> dict` writes 48k stereo float WAV and returns sample/coverage metadata. `process.run(args, *, cancelled, ...)` owns cancellable FFmpeg processes, never shell commands.

- [ ] Write tests for real FFmpeg stereo overlap, embedded/detached mute, nested trim/speed/gain/fades, missing streams, unsupported effects/keyframes/routing and exact duration. Assert a known overlapping impulse sums without automatic normalization and silent trim bounds remain silent.
- [ ] Run `python -m unittest discover -s tests -p test_harness_mix.py -v`; observe missing implementation failure.
- [ ] Implement strict inventory and chunked/memmap sum with bounded decoder concurrency. Validate actual stream metadata and refuse unknown audible semantics with segment IDs. Preserve input bytes.
- [ ] Run the task tests and existing 30 tests; expect all pass. Commit task files.

### Task 2: Measured speech leveling and previews

**Files:** `capcut_harness/speech.py`, `loudness.py`, `audio.py`, `assets/silero_vad.onnx`, third-party licenses; `tests/test_harness_audio.py`.

**Interfaces:** `audio.analyze(mix_path: Path, out: Path, params: dict, progress, cancelled) -> dict` produces stable interval IDs/times/before LUFS. `audio.render(analysis: dict, out: Path, params: dict, excluded: list[str], progress, cancelled) -> dict` returns measured report and before/after preview/master paths plus hashes. Parameters are validated centrally; intervals and excluded IDs must match the analysis.

- [ ] Write failing tests using runtime-generated spoken phrases at different gains plus silence and non-speech, with real VAD and FFmpeg. Assert detected speech, accepted-interval spread reduction, bounded gain, true peak <= -1.5 dBTP +0.1, sample duration, A/B alignment, exclusions and cancellation. Add short/no speech and clipped-source cases.
- [ ] Run `python -m unittest discover -s tests -p test_harness_audio.py -v`; observe missing implementation failure.
- [ ] Implement licensed local ONNX VAD, FFmpeg EBU R128 region measurements, gain envelope in bounded blocks, limiter with oversampled true-peak verification, PCM master and seekable previews. Measure same intervals after output; report unattained targets honestly. Keep long gaps at baseline gain.
- [ ] Run task and preceding tests; expect all pass. Commit task files and license provenance.

### Task 3: Native audio stage/apply/undo

**Files:** `capcut_harness/transaction.py`; `tests/test_harness_transaction.py`.

**Interfaces:** `transaction.stage(inventory, rendered, directory: Path) -> dict`, `apply(directory: Path) -> dict`, `undo(directory: Path) -> dict`, `verify(directory: Path) -> dict`. Stage binds all source/output/revision hashes, exact backups, new resource path, only root mute changes and new native track/material. Resource stays on undo.

- [ ] Write failing tests for exact compound/card preservation, native audio schema, all mirrors, busy guard, stale source/output, lock collision, app reopening, mid-write rollback/partial recovery, foreign edits, repeat apply/undo and refusal to re-normalize generated output.
- [ ] Run `python -m unittest discover -s tests -p test_harness_transaction.py -v`; observe missing implementation failure.
- [ ] Implement a journaled CAS transaction using existing shared lock and editor guard, safe resource creation, exact native root audio master at zero and exact-byte undo. Recheck target/evidence integrity for every retry.
- [ ] Run task and earlier tests; expect all pass. Commit task files.

### Task 4: Persisted jobs and validated action registry

**Files:** `capcut_harness/jobs.py`, `actions.py`, `service.py`; `tests/test_harness_jobs.py`.

**Interfaces:** `Service(state_dir: Path, project_roots: list[Path] | None)` offers `projects()`, `inspect(project_id)`, `dispatch(action: dict)`, `jobs()`, `job(job_id)`, `close()`. Actions: project.register/inspect, dialogue.analyze/render/apply/undo/cancel/retry and cards inspect/stage/apply/verify/restore with existing evidence validation. Typed commands parse to these same action objects; unknown or ambiguous commands never mutate. Job IDs and project IDs are generated server-side.

- [ ] Write failing tests for queue serialization, persisted progress/restart interrupted state, cancellation, retry revision separation, repeated request idempotency, exclusion/target rerender, typed command equivalence and unknown-command refusal. Exercise an actual pipeline on a disposable fixture.
- [ ] Run `python -m unittest discover -s tests -p test_harness_jobs.py -v`; observe missing implementation failure.
- [ ] Implement single-worker jobs with atomic store, private paths, validated capabilities and factual terminal states. Keep project writes exclusively inside transaction module.
- [ ] Run task and earlier tests; expect all pass. Commit task files.

### Task 5: Loopback HTTP and CLI

**Files:** `capcut_harness/server.py`, `__main__.py`; `tests/test_harness_server.py`.

**Interfaces:** `create_server(service, port=0) -> HTTPServer` binds `127.0.0.1`; routes `/api/bootstrap`, `/api/projects`, `/api/jobs`, `/api/jobs/<id>`, `/api/action`, `/api/command`, `/media/<job>/<allowlisted-name>` and bundled static assets. CLI `python -m capcut_harness [--port 0] [--state-dir PATH] [--project-root PATH] [--no-browser]` launches service; diagnostic `inspect`/`command` reuse registry without shell interpolation.

- [ ] Write failing HTTP tests for session/Origin/Host validation, oversized bodies, traversal/symlinks, JSON errors, media range access and unsupported methods, along with true API job execution and clean shutdown.
- [ ] Run `python -m unittest discover -s tests -p test_harness_server.py -v`; observe missing implementation failure.
- [ ] Implement local-only server, random session token, bounded requests, exact static/media allowlists and per-job media ownership. Return meaningful HTTP status/errors and no arbitrary file access.
- [ ] Run task and preceding tests; expect all pass. Commit task files.

### Task 6: Working browser workspace

**Files:** `capcut_harness/web/index.html`, `app.js`, `app.css`, `charts.js`, `fonts/`; `tests/browser_harness.mjs`, design notes.

**Interfaces:** UI consumes Task 5 JSON and media routes; all numbers and chart intervals come from API report. Screen routes: dialogue, jobs, cards; use actual capability status. One command box feeds `/api/command`. Dialogue flow selects project, analyzes/renders, edits exclusions/target, listens/seeks A/B, applies and undoes current revision.

- [ ] Write a headless browser acceptance script asserting real project selection -> job -> interval rows -> synchronized A/B -> apply -> undo against a disposable server fixture, plus busy/stale/errors and keyboard form controls. Run before UI and observe failure.
- [ ] Build responsive Vietnamese UI using dealt `true-black-flat` seed 492682947, local Inter, one data hue and signature speech-level timeline. Implement every state without fake controls or sample production data.
- [ ] Run browser acceptance and `node <taste>/scripts/lint.mjs --app capcut_harness/web`; run inspector at 1440/768/390. Read screenshots, fix FAILs and document any defended WARNs. Commit UI and tests.

### Task 7: Packaging, skill, real-project validation and public release

**Files:** `pyproject.toml`, `requirements.txt`, `install-harness.py`, `skills/capcut-harness/SKILL.md`, README Vi/En, `docs/verification.md`, installer tests.

**Interfaces:** Public one-line bootstrap installs a managed isolated environment, skill and launch command; pinned tag/source and dependency versions, safe repeat/update, Python 3.10+ check. Preserve old cards-only install.py and v0.1.1 install line.

- [ ] Write failing installer tests for safe extraction, unmanaged paths, old version backup, repeat install and command launch; run and observe failure.
- [ ] Implement package data inclusion, managed venv installer/launcher, skill and complete localized setup/compatibility/recovery docs. Validate licenses and sanitized release manifest.
- [ ] Run complete unit/integration/browser suite and isolated install, then actual read-only full 1027 analysis/render. Record measured coverage, spread, peak, duration and current-project preservation; do not apply to an open editor.
- [ ] Run one fresh whole-branch review required by executing-plans; fix important findings with RED->GREEN tests and rerun affected/full suites as justified.
- [ ] Integrate authorized branch, publish new public version/tag/release, run actual public installer in a clean isolated location and prove CLI/UI launch. Inspect remote files/release and final compatibility evidence before completion.
