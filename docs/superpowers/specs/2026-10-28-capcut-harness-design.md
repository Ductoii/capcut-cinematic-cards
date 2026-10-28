# CapCut Harness — local editor workspace

Status: design for user review. The user selected a local browser UI; detailed implementation below is the builder's proposal until approved.

## Intent and scope

Evolve the existing public cinematic-card tool into a local harness that receives button actions or typed commands, inspects CapCut projects, executes registered editing jobs, and exposes evidence, progress, apply, and undo. First editing module: make dialogue perceptually even across the whole project. Other sounds have lower priority. This is an extensible working editor assistant, not a claim to support every CapCut feature immediately.

The existing constraints persist: no computer use, no moving or retiming original shots, no re-encoding video, no changing title cards, no replacing original source media. Work remains on the user's computer. The user does not edit project JSON or configuration files manually.

## Approaches and decisions

The user chose a local browser UI over a separately packaged desktop app. A Python service bound only to loopback serves bundled HTML/CSS/JavaScript and runs background jobs; no cloud server, account, API key, or LLM dependency is required. Existing skill and CLI remain usable. A desktop wrapper can be added later without replacing the job API.

For audio, compare two viable approaches:

- Native gain automation: compact and editable, but CapCut volume-keyframe semantics are not yet validated in this project, and existing effects may make offline gain predictions inaccurate.
- Render an audio master and add it as a separate root audio track: measurable output, unchanged video and nested compound contents, and reversible. This is the proposed first implementation. Existing audible root segments are muted only when applying the master. Their exact prior values are backed up. No nested clip is changed.

An exported final movie may be used as an explicitly identified mix reference only if it matches the current edit; it is not silently substituted for live timeline data. The normal path derives the mix from the project's active timeline and source media.

## User flow

1. Launch using one command. Browser opens a local workspace with actual discovered projects, or a path field for another project. Show compatibility, duration, source counts, and editor state from current inspection.
2. Select a project and choose **Cân âm thoại**. Defaults: dialogue target -18 LUFS, maximum boost 12 dB, output true-peak ceiling -1.5 dBTP. These are product defaults, not a claim of a mandatory delivery standard. Advanced controls remain optional.
3. A persisted job snapshots the project and sources, maps all audible nested media, reconstructs the supported audio mix, detects speech, and measures speech regions. Progress names the real stage and completed work; unknown remaining time is not invented.
4. Show detected speech intervals with before/after loudness, gain, exceptions, source coverage, and full-film timeline. Provide synchronized A/B preview, jumping to an interval and excluding a false speech detection without file editing. Exclusions or target changes produce a new render/review revision; they cannot apply a stale result.
5. Apply is available only for a completed, current, verified revision. It adds the generated audio master at time zero, mutes original root audio paths, synchronizes supported draft mirrors, and verifies preservation. If CapCut is open, keep the job ready with a clear save-and-close message; never kill the application or write past the guard.
6. Undo restores exact saved draft bytes while they still match the known transaction state. Refuse to overwrite subsequent user edits. Keep the generated WAV and job evidence until explicit cleanup; do not remove source media.

Buttons and typed commands use the same validated action registry. Supported natural phrases are documented and deterministic, for example `phân tích 1027`, `cân âm thoại 1027`, `áp dụng <job>`, `hoàn tác <job>`. An unrecognized or ambiguous request receives supported choices and performs no mutation; commands are never executed as shell text. This initial command interface is not marketed as unrestricted AI chat.

## Harness architecture

Concrete starting point: repository `https://github.com/Ductoii/capcut-cinematic-cards`, current `main` at `37ecc196c357ec9cf677e7dbdf6f859d68e27018`. Extend this repository; publish a new tagged release, retaining the cards-only v0.1.1 installer contract. Initial validated platform is macOS with Python 3.10+ and FFmpeg/ffprobe. Other OS support is advertised only after corresponding validation; browser UI portability alone does not prove native project compatibility.

Reuse `skills/capcut-cinematic-cards/scripts/cards.py`: `load()` resolves `Timelines/project.json.main_timeline_id`, enforces semantic equality of root/main `draft_info.json`, and selects existing `draft_info.json`, `draft_info.json.bak`, and `template-2.tmp` in root and indexed-main directories. Never write `template.tmp`, index, alternate timelines or metadata. Only readable unencrypted JSON schema 360000 is supported; an app build number by itself does not imply compatibility. `locked(project)` uses exclusive creation of `.capcut-cards.lock`; the harness acquires this exact lock while mutating. Never remove a lock based on elapsed time alone.

Use and strengthen `cards.editor_running()` process detection for the target platform: block when any main CapCut editor process is running, including alternative installed application paths/names and detection failures. Background helpers alone are not proof of an active editor. This guard is conservative and cannot inspect unsaved state; saving/closing the application is the user-visible prerequisite. Hash/CAS checks protect disk state in addition to the process guard. Validation reports must explicitly say `editor_render_verified: false` unless real native evidence exists. Offline measured audio plus native-draft preservation/integrity proves the v1 apply operation; it does not prove a native CapCut render. These are separate UI/report fields.

- Capability registry: project list/inspect, dialogue analyze/render/apply/undo, existing card inspection/staging/apply/verify/restore adapters. Card authoring retains its current evidence requirements; the UI must not claim that entering a character name automatically proves identity or timing.
- Project adapter: reuse readable schema 360000 root/main-timeline resolution and placeholder paths. Enumerate nested compounds with affine trim/speed mapping. Preserve all unrelated project fields and ownership state.
- Job store outside projects: per-job manifest, immutable source snapshot/hash inventory, parameters, logs, progress, analysis, previews, output hashes, transaction, and exact backups. On restart, unfinished jobs become interrupted, never falsely successful; the UI offers retry as a fresh job. Repeated mutation requests are idempotent per job/revision.
- Single worker/mutation queue to bound CPU and serialize writes. Cancellation stops owned child processes and leaves project untouched before apply. Jobs expose actual terminal state and errors. Restarting the UI does not restart a live worker behind its back.
- API: typed JSON actions with server-generated project/job IDs, bounded request sizes, local session token, Origin/Host checks, no CORS wildcard, no arbitrary command/process/file serving. Media preview endpoints expose only job-owned preview files with range support. Loopback access is not treated as sufficient CSRF protection.
- CLI and UI are clients of the same Python API. A skill documents installation, launch, compatibility, command vocabulary, evidence interpretation, and recovery. README provides one-line installation/launch and update behavior. Existing v0.1.1 installation remains supported.

## Audio reconstruction and leveling

Inspect each audible source and relevant ancestor first. Include embedded video audio, detached audio, overlapping music/effects, trimming, constant speed, segment/ancestor volume, supported mute flags and linear fades. Probe actual audio streams rather than trusting `has_audio`. Apply ancestor trims and fades in the correct timeline coordinate system. Mix in float at 48 kHz stereo without implicit `amix` normalization. Avoid clipping the intermediate.

Refuse to render/apply when required sound cannot be reconstructed: missing media, ambiguous/external compounds, reverse/loop/curve speed, unsupported audio effects, custom channel routing, vocal separation, unsupported gain keyframes or audio-bearing transitions. Report exact affected segments, not a generic success. Visual-only effects do not block audio. Identify limitations in the job report and never call a source reconstruction a native CapCut render.

Use local speech detection (Silero VAD through an installed, pinned runtime/model) to find candidate dialogue regions. VAD is not speaker identification or music separation. Merge very short adjacent detections, avoid silence-driven boosts, and review uncertain regions. The harness must allow excluding detections and rerendering. Speech mixed with music is leveled as a mix; music changes with it. Do not promise isolated voice processing.

Measure speech loudness using FFmpeg's EBU R128/BS.1770-compatible analysis, not whole-file peak normalization. Derive bounded gain per phrase, smoothly interpolate between phrase gains, avoid pumping in short gaps, and keep long non-speech regions at baseline gain. Apply conservative limiting to the final mix, then remeasure output true peak and actual speech loudness. Intervals that cannot reach the target within the gain/peak constraints remain explicitly marked; target attainment is measured after rendering rather than assumed from requested gain. Preserve natural voice dynamics within each phrase rather than making every sample equal.

Before/after statistics must use identical accepted speech intervals. Report median, percentile spread, deviations from target, limiting exceptions, and non-speech coverage. Show measured numbers only. Full mix and output sample counts match the project duration within one audio sample; preview alignment does not drift. PCM 24-bit WAV output avoids another lossy audio generation. Speech processing and previews stay outside the project until apply.

## Project mutation and recovery

Snapshot all existing supported draft mirror files and verify stable reads. Bind a review to hashes of project, source media, parameters, detection edits, staged draft, output WAV, and previews. Recheck before applying, including retries. Share the existing card transaction lock so the two tools cannot mutate a project simultaneously. Recheck editor state and CAS immediately before every write. No symlink or path traversal targets.

At apply, atomically copy the verified WAV into a harness-owned project resource path, append one native audio material and root track, and mute only original audible root segments. Existing card materials/tracks and nested compounds compare exactly with baseline. Reset any inherited fields in the new audio material/segment so it has no old fades, speed, effects or routing. Synchronize root/indexed-main mirrors only. Do not rewrite timeline index or unrelated metadata.

Each file write is atomic; multi-file updates are journaled, with guarded rollback and recovery for partial writes. Never roll back over a foreign edit. Undo is conditional on current hashes and restores exact original bytes, including state files if written. The native editor's render has not been verified until actual native evidence exists; report file integrity and offline audio verification separately.

Repeated normalization starts from backed-up original audio configuration or refuses an incompatible changed project. It must never normalize its own output repeatedly, mix original and generated master twice, or silently delete prior user changes.

## Frontend design

Use the explicitly requested `design-taste-frontend` app workflow. Dealt style: **true-black-flat**, seed **492682947**, no redraw. Localize UI copy in Vietnamese. Neutral black ground, brightness steps, quiet controls, white primary action, one restrained audio-meter hue on data. Load the selected Inter face locally with its redistribution license. No remote font dependency during normal use.

Main screen question: **Thoại đã đều và bản nào sẵn sàng áp dụng?** The lead is the real speech-level timeline and A/B control. Project scope and schema compatibility appear in the shell. Side panel holds target, actual job state, and apply/undo. History is a working list with actual outcomes. Product identity comes from a drawn waveform/cut mark and the accepted speech intervals, not invented metrics or decorative waveforms.

At desktop 1440x900, show project scope, primary action, timeline, preview, first interval rows and job state above the fold. At tablet, fold navigation and stack panels when they cannot fit. At 390 px, use one pane at a time and retain touch controls and complete interval details. All empty/loading/error/cancelled/interrupted/busy/stale/applied/restored states must be truthful. Keyboard focus, form labels, reduced-motion behavior, and contrast are checked. No decorative motion.

## Verification and deliverables

- Existing 30 card/installer tests remain green.
- Audio tests use real speech fixtures with known level differences, silence, non-speech content, overlapping sources, trims, speed, fades and nested gain. Confirm reduced accepted-speech loudness spread and measured peak ceiling, plus duration/alignment and no silence amplification. Do not use sine waves to prove speech detection.
- Integration tests exercise actual FFmpeg and VAD, apply/undo on synthetic native drafts, compound/card preservation, mirror synchronization, busy editor, stale/evidence tampering, concurrent jobs, cancellation, recovery, and repeated normalization.
- API tests cover command/button equivalence, invalid requests, session/Origin/Host checks, traversal, job transitions, media access and restart behavior.
- Browser tests click the full project -> job -> A/B -> apply -> undo flow against disposable fixture projects, including error/busy/stale states. No Computer Use. Headless browser verification and screenshots at 1440/768/390 follow the design skill; inspect and fix actual layout failures.
- Run a read-only analysis and A/B render for real project 1027. Its editor is currently open; do not apply during development. User can apply later through the completed UI after saving/closing. A real-project apply is not a prerequisite to proving safe mutation against representative fixtures.
- Publish reviewed source, skill, one-line install/launch instructions, compatibility limits and a versioned public release in the existing authorized repository. Publish no private project paths, assets, audio, frames or generated masters. Verify clean-machine-style installation in an isolated environment.

Completion means the UI drives a working harness and the first full dialogue-normalization workflow is verified, not merely a visual mockup or a renamed cards CLI. Unimplemented future modules are extension points, not fake working controls.

## Builder choices

The builder may choose pinned Python dependencies, package layout, persistence format, preview codec, short-time gain interpolation and limiter implementation within the measurable requirements above. Prefer a small dependency surface and no frontend build pipeline unless needed. Record defaults and actual limitations. Do not add authentication accounts, cloud sync, billing, auto-update infrastructure or speculative modules.
