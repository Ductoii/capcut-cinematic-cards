# CapCut Cinematic Cards

[Tiếng Việt / full guide](README.md)

A local Codex skill for necessary **time cards, location cards and first-appearance character introductions**, with typography adapted to each film. Separate editable text tracks preserve existing compound clips, audio, timing and transitions. No computer use, MCP server or separate API key.

## One-line install

macOS/Linux, Python 3.10+:

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.1.0/install.py | python3
```

Windows PowerShell, Python 3.10+:

```powershell
(Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.1.0/install.py).Content | py -3 -
```

This downloads and executes the public [installer](install.py), pinned to version 0.1.0. It installs at `~/.agents/skills/capcut-cinematic-cards`. Restart Codex if discovery has not refreshed. Reinstalling backs up a previous managed install; unmanaged skills are preserved. Set `CAPCUT_CARDS_SKILLS_DIR` for another skills directory. Skill backups are stored in the sibling `capcut-cards-install-backups` folder.

You can also give this repository URL to local Codex and ask it to install the skill and prepare dependencies. No Git clone or manual JSON editing is required.

## Tell Codex

```text
$capcut-cinematic-cards
Add only necessary time/location cards and introduce principal characters at
their first confirmed appearance in project "My Film". Match the film's style.
Prefer existing black fades, protect important shots, reactions and dialogue,
and preserve my compound clip. No computer use.
The screenplay and character references are at: [local path or attachment].
```

Codex discovers the project, reads the screenplay/captions, reviews source frames and audio, chooses safe placements, fills the plan, stages backups, applies and verifies. Save and close CapCut before applying: the helper refuses a running editor and never kills it. Analysis/staging can finish while the editor is open.

Character identities require evidence and a review of earlier scenes. Unknown identities, mystery reveals and unsuitable entrance scenes are omitted or deferred. This is editorial judgment, not guaranteed automated face recognition.

Five starting themes cover heritage drama, modern thriller, documentary, intimate romance and noir. Codex chooses an installed font and can adjust color, size, spacing, position and opacity fades. No fonts are bundled. Animated tracking, moving titles, glitches, freeze frames and effect packs are outside this version. A 1.5s fade is never stretched into black just to hold a 3.4s card.

## Requirements and boundaries

- Local Codex with filesystem/terminal access, Python 3.10+, FFmpeg and ffprobe on PATH, accessible source media and an installed font supporting the film's language. Ask Codex to prepare missing dependencies.
- Unencrypted CapCut JSON draft schema **360000** only. Other schemas stop safely. Source mapping supports nested compounds, trims and constant speed; reverse, loops, speed curves and external compounds need separate evidence or omission.
- Source frames are **uncomposited**, and audio outputs are separate stems with global offsets. Codex must inspect crop, transforms, effects, captions and overlays too. Successful file verification is not CapCut rendering/playback verification.
- File/media workflow and 27 tests verified locally on macOS. The file tests are portable but have not been run on Windows/Linux; CI is not enabled. Native CapCut rendering there has not been verified. Linux can inspect/edit copied compatible draft files, not run a bundled CapCut editor.
- Exact ownership hashes prevent replacing modified cards. CapCut normalization can trigger this guard; inspect and preserve changes instead of forcing an old plan.
- Backups live outside the project. Guarded restore refuses to overwrite later unfamiliar edits. Multi-file apply is not crash-atomic; the saved transaction supports recovery from known partial writes.

The skill has no media-upload service. Projects, frames, audio, fonts and backups stay in local files; material supplied to the Codex session is still handled according to that session's data settings.

Ask Codex to restore a previous card run or remove only this skill when needed. Neither action requires you to edit draft files. Project backups are separate from the installed skill.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Tests cover original-track preservation, mirror synchronization, speech protection, character evidence, styling, stale sources, busy editor, owned updates, guarded rollback, source mapping and installer safety. [Agent workflow](skills/capcut-cinematic-cards/SKILL.md) · [Commands/plan](skills/capcut-cinematic-cards/references/tool.md) · [Editorial guide](skills/capcut-cinematic-cards/references/editing.md) · [MIT license](LICENSE)
