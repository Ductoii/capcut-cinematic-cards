# v0.2.0 verification evidence

Platform: macOS, Python 3.12.14, NumPy 2.2.6, ONNX Runtime 1.23.2, local FFmpeg/ffprobe and Chrome. First supported editor format: readable unencrypted CapCut JSON schema 360000. Other OS/editor versions remain unverified.

## Automated behavior

66 unit/integration tests passed after the final whole-branch review and its regression fixes. These include the retained 30 card tests, actual FFmpeg mix and Silero VAD, bounded loudness windows, measured gain/peak/duration, strict audio coverage, exact native transaction/Undo and foreign-edit preservation, cancellation/restart/revision guards, local HTTP session/Origin/Host/media-range boundaries, CLI completion and live-service routing, and installer extraction/upgrade/failure behavior. A real child-process hard exit during an indexed multi-mirror Apply is recovered through service restart/Retry, followed by exact Undo. Saves during staging, new mirrors and an obsolete Apply waiting in the queue are refused.

Headless Chrome exercised real generated speech through project selection, analyze, interval rows/seeking, synchronized A/B, editor-busy rejection, Apply, exact Undo, stale-project rejection and unsupported commands. Settings remain visible with no horizontal overflow at 1440/768/390. Taste inspection: 0 FAIL at those widths; deliberate independent panel heights and native audio control chrome explain two measurement warnings. See ui-design.md. No Computer Use or CapCut UI automation was used.

The managed installer was run in a clean directory containing spaces: private venv, dependency installation, ONNX model inference and launcher startup passed. A wheel was built with the bundled card backend, model/notices, web assets and font/notices. Public-tag installation is checked again after publication.

## Real film, read-only

A complete 1,779.366666-second local project was analyzed without applying changes. It contains 86 actual audible source segments; 75 separated embedded video tracks are omitted to avoid duplicating detached audio. There were no unsupported audible semantics. The output contains 85,409,600 stereo samples at 48 kHz.

| Measurement | Original | Processed |
|---|---:|---:|
| Voice-activity intervals | 322 | 322 |
| Speech median | −12.98 LUFS | −18.00 LUFS |
| Speech P10–P90 spread | 6.03 LU | 0.05 LU |
| True peak | — | −1.70 dBTP |
| Accepted intervals outside ±2 LU target | — | 0 |

The final complete API/UI run reproduced these values and preserved all project/mirror hashes. Separate quality review found 27 low-score VAD candidates, no decoded source segments near full scale, 56,592 reconstructed-mix samples near full scale, and 185/88,968 measured 20 ms windows with attenuation over 0.5 dB after limiting (maximum RMS attenuation 7.667 dB). Those flags remain visible for listening review; the 27 candidates were not silently excluded.

These are **measurements of the reconstructed mix**, not a promise about every film or proof of native editor rendering. A short source/native-export comparison independently confirmed the separated-audio inventory choice. VAD can include vocals/music and miss speech; mixed music changes with speech gain. Separate quality evidence retains interval VAD scores, near-full-scale samples before source timeline gain, mix near-full-scale samples and measured 20 ms RMS attenuation after limiting. These are review flags, not proof of distortion or calibrated confidence. Singing/music-vocal classification remains unassessed. Zero target deviations does not imply zero quality flags. Full reports and recordings remain private on the user's machine.

Apply and Undo were verified on disposable native-schema projects, including compound/card structural preservation and byte-exact original mirror restoration. The real film was open in CapCut, so it was only read/analyzed. No actual-project write or native CapCut playback/export is claimed; `editor_render_verified` remains false.

## Release boundaries

The public repository contains code, documentation, tests, the licensed VAD model and local font. It excludes private project/media paths, film audio/video, generated job outputs, installation environments, recordings and credentials. The old standalone v0.1.1 card installer remains available unchanged. The v0.2.0 installer adds the full harness and both skills.

## v0.3.0 delivery — 2026-10-28

Scope follows the owner's explicit opt-out from additional recheck/review, a 300-source exercise and a real-film listening run.

- Python compilation, JavaScript syntax and Git whitespace checks passed.
- Wheel built with card backend, source engine, MCP transport, ONNX model and UI assets present.
- Managed local installation completed with NumPy/ORT; native Codex CLI accepted marketplace/plugin registration.
- Installed stdio MCP returned initialization, six tools, a workspace connection and a self-contained `text/html;profile=mcp-app` resource.
- Initial discovery exceeded the original eight-second startup grace; increased it to 25 seconds.
- Host rendering and UI-to-chat message delivery have not been observed in this already-open chat. A fresh chat must discover the plugin tools. No native CapCut playback/export or listening-quality claim is made for v0.3.0; historical tests below/above apply to their recorded versions only.

## v0.3.1 — project catalog and screenplay submission

Local discovery reads CapCut stores/indexes, configured paths and OS search metadata without validating every timeline. A metadata-only scan found 289 project folders before expanding OS search to root draft files. A disposable script-storage run confirmed that a request keeps its submitted revision after a newer screenplay is saved. Python/JavaScript syntax and package checks are the scope for this update; no audio/full-film recheck, editor write or native host bridge claim.
