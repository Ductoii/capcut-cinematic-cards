# Harness development

Python package: `capcut_harness`. Install with Python 3.10–3.13: `python -m pip install .`; external FFmpeg/ffprobe are required. The wheel includes the card backend, ONNX model/license, web assets and local font/license. End users should prefer the managed source installer, which also installs both Codex skills.

Launch: `python -m capcut_harness --no-browser --state-dir /tmp/own-state --project-root /path/to/projects`. Port defaults to an available loopback port. Output includes the URL. Existing-state launches connect to the running service; avoid unrelated programs sharing a state directory.

## API

GET `/api/bootstrap` returns a random session token and sets a SameSite Strict cookie. Mutations require JSON, `X-Harness-Token` and matching `Origin`. Host is restricted to the actual local port. The server binds IPv4 loopback only. GET `/api/projects`, `/api/projects/<id>`, `/api/jobs`, `/api/jobs/<id>` require a token or session cookie. POST `/api/action` and `/api/command` share `Service.dispatch`.

Actions: project.register/inspect; dialogue.analyze/render/apply/undo/cancel/retry; cards.inspect/stage/apply/verify/restore. Render takes the parent `job_id`, `params` and excluded interval IDs. Reusing a `request_id` with the same action returns its original ticket; conflicting reuse is refused. Dialogue preparation/mutation is serialized by one worker; cards adapters retain their existing synchronous transaction/lock behavior. Both use `.capcut-cards.lock` when mutating a project.

Jobs persist under state/jobs/<id>; all media serving is allowlisted and bound to that job directory. Audio byte ranges support seeking. A restart marks unfinished jobs interrupted; Retry creates a new analysis or resumes the saved apply/undo transaction, with current hashes and editor checks. Backups and evidence must remain intact. CLI commands poll the same records to completion.

## Tests

```bash
python -m unittest discover -s tests -q
PLAYWRIGHT_MODULE=/absolute/path/to/playwright node tests/browser_harness.mjs
```

Tests require FFmpeg. Real VAD tests synthesize self-authored speech with macOS `say` (Samantha) or `espeak`; they skip if neither exists. Browser tests require Playwright and Chrome; set `HARNESS_PYTHON` and `CHROME_PATH` for custom locations. Fixture audio/projects are disposable and never production data. Browser automation tests this app only and does not control CapCut.

Build: `python -m pip wheel . --no-deps`. Installer tests inject a lightweight environment builder; separately perform a real clean install and verify NumPy/ORT, ONNX inference, HTTP/UI, and wheel assets from outside the checkout. Public release checks are recorded in verification.md.

## Audio and transaction boundaries

Timeline adapters refuse unmodeled audible semantics. Mix reconstruction uses disk-backed float32 stereo and bounded decoder concurrency. Separated video audio is omitted to avoid doubling its detached track. Silero VAD is local and recurrent; each detected region is measured through a bounded FFmpeg input window. Phrase gains interpolate smoothly; oversampled limiting precedes actual post-render interval/true-peak checks. Reports distinguish target attainment from bounded-gain exceptions.

Apply stages exact original mirrors and a preservation proof, then checks source/review/project hashes under the shared project lock. It writes an owned resource first, draft mirrors next, ownership state last, with a journal. Known partial writes can recover; rollback preserves foreign bytes and their possible generated-media dependencies. Undo is guarded and leaves the generated WAV for safety. Native playback is a separate verification step; file integrity alone must never set editor_render_verified true.
