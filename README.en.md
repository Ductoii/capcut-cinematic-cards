# CapCut Harness + Cinematic Cards

**A local browser workspace for whole-film dialogue leveling, synchronized A/B and Apply/Undo, plus evidence-led time, location and character name + role cards.**

[Tiếng Việt](README.md) · [v0.2.0 release](https://github.com/Ductoii/capcut-cinematic-cards/releases/tag/v0.2.0) · [Verification](docs/verification.md) · [MIT](LICENSE)

Media stays on your computer. No Computer Use, API key or audio cloud account. Buttons and the command box share one harness. Commands use a finite vocabulary, not unrestricted AI chat. Your current Codex session makes editorial decisions for cards.

## One-line harness installation

On **macOS**, first have **Python 3.10–3.13, FFmpeg and ffprobe** on PATH. NumPy and ONNX Runtime go into a private environment; global Python is unchanged. macOS is the tested platform; Linux/Windows have not been fully validated.

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.2.0/install-harness.py | python3
```

Not comfortable with Terminal? Give this repository link to **local Codex on the computer containing your project** and say:

> Install CapCut Harness v0.2.0, prepare missing dependencies and open its local UI. No Computer Use.

The installer downloads the pinned v0.2.0 tag, builds a private environment, and installs **both skills** into `~/.agents/skills`. Reinstalling keeps the previous release and backs up the skill/launcher. Unmanaged locations are preserved. No cloning or JSON edits. Restart Codex if it has not discovered the new skill.

Launch:

```bash
~/.local/bin/capcut-harness
```

Keep that Terminal running. The browser opens a `127.0.0.1` address on this computer. Launching again opens the existing service. `Ctrl+C` safely stops it; relaunch to see saved jobs. Keep `~/.local/share/capcut-harness`: it contains listening versions, reports and Undo backups. A long film can use several GB.

## Dialogue workflow

1. Choose a project in the top bar. Use **Thêm project** (Add project) if missing; local Codex can locate its folder for you.
2. Press **Cân âm thoại** (Level dialogue). It reads the timeline/media, finds voice activity, measures intervals and prepares listening files. The project is unchanged. Progress, cancel and retry are available.
3. Review P10–P90 spread, median speech and true peak. Click a table interval to listen; **Bản gốc / Sau xử lý** switches original/processed at the same position.
4. Uncheck false detections or change target/maximum gain/ceiling, then press **Cập nhật bản nghe** (Update listening version). Apply accepts the latest review revision; older jobs remain in **Công việc** (Jobs).
5. Listen and approve the result. **Save and close CapCut**, then press **Áp dụng vào project** (Apply). The harness adds one root audio master and mutes audible original root segments to avoid duplicate playback. Video, nested compound and card structures are preserved.
6. Reopen CapCut and check actual playback. To undo, save and close CapCut and press **Hoàn tác** on the applied job. If the project changed, restoration stops to preserve your edits; ask Codex to compare backups instead of manually overwriting drafts.

Defaults: −18 LUFS speech, maximum boost/cut 12 dB, whole-master ceiling −1.5 dBTP, stereo 48 kHz PCM24. Actual post-render measurements determine attainment; exceptions are reported. Excluded intervals receive zero gain; the final limiter still protects the complete master.

The UI separately reports low VAD scores, source/mix samples near full scale and measured attenuation after limiting. These are listening-review flags, not proof of clipping or calibrated recognition confidence. Music-vocal classification remains unassessed.

**Audio limitations:** VAD finds voice activity; it does not separate stems, identify characters, translate or transcribe. Music/SFX mixed into speech changes level with that interval. Singing, very short or noisy speech can be misclassified. Listen and exclude as appropriate. Leveling works between phrases while preserving variation inside each phrase.

**Compatibility:** readable, unencrypted local CapCut JSON schema `360000`, tested on macOS. Unknown audible effects, routing, variable speed or mute flags are refused. A source-reconstructed mix is not proof of native CapCut rendering; reports keep `editor_render_verified: false`. Not every CapCut version/project is supported.

## Codex and command box

```text
$capcut-harness
Level dialogue in project 1027, prepare A/B and show remaining deviations.
Preserve picture, compound clips and cards.
```

Supported commands: `phân tích <project>` / `inspect`, `cân âm thoại <project>` / `normalize dialogue`, `áp dụng <job>` / `apply`, `hoàn tác <job>` / `undo`, `thử lại <job>` / `retry`. Select ambiguous project names in the UI. Unknown commands do nothing. The Cards view lists existing text; use the card skill below for character/scene analysis and placement.

CLI: `capcut-harness --help`, `capcut-harness inspect /path/to/project`, `capcut-harness command "normalize dialogue Film name"`. CLI waits for completion and connects to the running UI service. [Developer guide](docs/harness-development.md).

## Standalone cinematic cards

The guide below covers the standalone cards tool. Its v0.1.1 installer installs only that skill, without the harness/audio environment. The v0.2.0 harness installer above already includes it.


[Tiếng Việt / full guide](README.md)

A local Codex skill for necessary **time cards, location cards and first-appearance character introductions**, with typography adapted to each film. Separate editable text tracks preserve existing compound clips, audio, timing and transitions. No computer use, MCP server or separate API key.

## One-line install

macOS/Linux, Python 3.10+:

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.1.1/install.py | python3
```

Windows PowerShell, Python 3.10+:

```powershell
(Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.1.1/install.py).Content | py -3 -
```

This downloads and executes the public [installer](install.py), pinned to version 0.1.1. It installs at `~/.agents/skills/capcut-cinematic-cards`. Restart Codex if discovery has not refreshed. Reinstalling backs up a previous managed install; unmanaged skills are preserved. Set `CAPCUT_CARDS_SKILLS_DIR` for another skills directory. Skill backups are stored in the sibling `capcut-cards-install-backups` folder.

You can also give this repository URL to local Codex and ask it to install the skill and prepare dependencies. No Git clone or manual JSON editing is required.

## Tell Codex

```text
$capcut-cinematic-cards
Add only necessary time/location cards and introduce principal characters with
their names and short established roles at
their first confirmed appearance in project "My Film". Match the film's style.
Prefer existing black fades, protect important shots, reactions and dialogue,
and preserve my compound clip. No computer use.
The screenplay and character references are at: [local path or attachment].
```

Codex discovers the project, reads the screenplay/captions, reviews source frames and audio, chooses safe placements, fills the plan, stages backups, applies and verifies. Save and close CapCut before applying: the helper refuses a running editor and never kills it. Analysis/staging can finish while the editor is open.

Version **0.1.1** defaults to **name + role**: a concise established occupation or relationship, never a villain label or a future reveal. Readable native sizes 6.2/3.8 and lower-third positions -0.64/-0.77 apply to character cards, with film-specific overrides. Time/location defaults are unchanged. Names-only requests, unknown roles or spoiler-sensitive roles require a documented omission reason; the assistant must never invent a role.

Character identities require evidence and a review of earlier scenes. Unknown identities, mystery reveals and unsuitable entrance scenes are omitted or deferred. This is editorial judgment, not guaranteed automated face recognition.

Five starting themes cover heritage drama, modern thriller, documentary, intimate romance and noir. Codex chooses an installed font and can adjust color, size, spacing, position and opacity fades. No fonts are bundled. Animated tracking, moving titles, glitches, freeze frames and effect packs are outside this version. A 1.5s fade is never stretched into black just to hold a 3.4s card.

## Requirements and boundaries

- Local Codex with filesystem/terminal access, Python 3.10+, FFmpeg and ffprobe on PATH, accessible source media and an installed font supporting the film's language. Ask Codex to prepare missing dependencies.
- Unencrypted CapCut JSON draft schema **360000** only. Other schemas stop safely. Source mapping supports nested compounds, trims and constant speed; reverse, loops, speed curves and external compounds need separate evidence or omission.
- Source frames are **uncomposited**, and audio outputs are separate stems with global offsets. Codex must inspect crop, transforms, effects, captions and overlays too. Successful file verification is not CapCut rendering/playback verification.
- File/media workflow and 30 tests verified locally on macOS. The file tests are portable but have not been run on Windows/Linux; CI is not enabled. Native CapCut rendering there has not been verified. Linux can inspect/edit copied compatible draft files, not run a bundled CapCut editor.
- Exact ownership hashes prevent replacing modified cards. CapCut normalization can trigger this guard; inspect and preserve changes instead of forcing an old plan.
- Backups live outside the project. Guarded restore refuses to overwrite later unfamiliar edits. Multi-file apply is not crash-atomic; the saved transaction supports recovery from known partial writes.

The skill has no media-upload service. Projects, frames, audio, fonts and backups stay in local files; material supplied to the Codex session is still handled according to that session's data settings.

Ask Codex to restore a previous card run or remove only this skill when needed. Neither action requires you to edit draft files. Project backups are separate from the installed skill.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Tests cover original-track preservation, mirror synchronization, speech protection, character evidence, styling, stale sources, busy editor, owned updates, guarded rollback, source mapping and installer safety. [Agent workflow](skills/capcut-cinematic-cards/SKILL.md) · [Commands/plan](skills/capcut-cinematic-cards/references/tool.md) · [Editorial guide](skills/capcut-cinematic-cards/references/editing.md) · [MIT license](LICENSE)
