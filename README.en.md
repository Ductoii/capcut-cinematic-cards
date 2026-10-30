# CapCut Cinematic Cards

**Audio is a separate tool:** [CapCut Audio](https://github.com/Ductoii/capcut-audio) runs local algorithms without Codex. This repository contains only the standalone cards skill.


[Tiếng Việt / full guide](README.md)

A local Codex skill for necessary **time cards, location cards and first-appearance character introductions**, with typography adapted to each film. Separate editable text tracks preserve existing compound clips, audio, timing and transitions. No computer use, MCP server or separate API key.

## One-line install

macOS/Linux, Python 3.10+:

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.1.3/install.py | python3
```

Windows PowerShell, Python 3.10+:

```powershell
(Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.1.3/install.py).Content | py -3 -
```

This downloads and executes the public [installer](install.py), pinned to version 0.1.3. It installs at `~/.agents/skills/capcut-cinematic-cards`. Restart Codex if discovery has not refreshed. Reinstalling backs up a previous managed install; unmanaged skills are preserved. Set `CAPCUT_CARDS_SKILLS_DIR` for another skills directory. Skill backups are stored in the sibling `capcut-cards-install-backups` folder.

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

Character cards default to a name plus a concise established role. Font, size and placement follow the supplied reference and actual scene; defaults are not a visual standard for every film. Names-only, unknown or spoiler-sensitive roles need a documented omission reason.

Character identities require evidence and a review of earlier scenes. Unknown identities, mystery reveals and unsuitable entrance scenes are omitted or deferred. This is editorial judgment, not guaranteed automated face recognition.

Five starting themes cover heritage drama, modern thriller, documentary, intimate romance and noir. Codex chooses an installed font and can adjust color, size, spacing, position and opacity fades. No fonts are bundled. Animated tracking, moving titles, glitches, freeze frames and effect packs are outside this version. A 1.5s fade is never stretched into black just to hold a 3.4s card.

## Fixes under trial

- Join the correct screenplay/production version to retained VIDEO trim/speed, inspect earlier appearances and whole holds on both sides of cuts, and anchor named days to explicit story cues.
- New plans require pinned evidence and independent review of every staged card before apply. Geometry review reconstructs supported static zoom/pan and overlays; declared rectangles are not measured glyphs.
- Reviewed paired native appearances preserve title/detail rich styling, shadows and independent scale fields; Codex prepares and pins the local template.
- Optional calibrated visible-text previews place the actual font over moving footage. Codex prepares private observed calibration; users do not edit JSON. Requires Pillow only for this command; it does not certify native CapCut rendering or auto-shrink overflow.
- Native subtitle templates preserve editable words/timing/recognition. Reviewed exact-ID position/wrap overrides protect individual actions; conflicting wrapping for shared materials stops safely.
- Reviewed native in/out resource pairs and justified short holds retain a reading plateau without starting in the wrong scene to satisfy a fixed duration.

## Version v0.1.3

- Small identifiers may appear during dialogue; reviewed simultaneous groups use separate person-associated editable labels.
- Fonts are configurable per card. Restyles preserve omitted typography fields; explicit layout repairs synchronize scale, widths and reviewed placement. No font or visual theme is mandatory.

- Probe exact last-frame boundaries and sub-frame video/audio tails with real sample timestamps and warnings; reject longer bad trims. Use compatible JPEG pixel format.
- Restyle saved owned titles without resetting wording, positions, timing, keyframes, effects or CapCut-normalized defaults. Changed hashes require a fresh recorded ownership review, never a pre-emptive state rewrite.
- Account for every requested principal in `character_review`, including shared pair cards and explicit omission reasons. Anchor scene cards to original fades and bridge short fades without extending black.
- Optionally reuse a reviewed existing local native entry animation on both text lines. No guessed/downloaded effects. An `ending` card uses an existing safe final hold.
- Explain Save and Quit (Cmd+Q on macOS) when closing a window leaves CapCut running.

See the [command/plan reference](skills/capcut-cinematic-cards/references/tool.md). Structural checks still do not verify native CapCut playback/rendering.

## Requirements and boundaries

- Local Codex with filesystem/terminal access, Python 3.10+, FFmpeg and ffprobe on PATH, accessible source media and an installed font supporting the film's language. Ask Codex to prepare missing dependencies.
- Unencrypted CapCut JSON draft schema **360000** only. Other schemas stop safely. Source mapping supports nested compounds, trims and constant speed; reverse, loops, speed curves and external compounds need separate evidence or omission.
- Source frames are **uncomposited**, and audio outputs are separate stems with global offsets. Codex must inspect crop, transforms, effects, captions and overlays too. Successful file verification is not CapCut rendering/playback verification.
- File/media tests verified locally on macOS. The file tests are portable but have not been run on Windows/Linux; CI is not enabled. Native CapCut rendering there has not been verified. Linux can inspect/edit copied compatible draft files, not run a bundled CapCut editor.
- Exact ownership hashes prevent replacing modified cards. CapCut normalization can trigger this guard; inspect and preserve changes instead of forcing an old plan.
- Backups live outside the project. Guarded restore refuses to overwrite later unfamiliar edits. Multi-file apply is not crash-atomic; the saved transaction supports recovery from known partial writes.

The skill has no media-upload service. Projects, frames, audio, fonts and backups stay in local files; material supplied to the Codex session is still handled according to that session's data settings.

Ask Codex to restore a previous card run or remove only this skill when needed. Neither action requires you to edit draft files. Project backups are separate from the installed skill.

## Development

```bash
python3 -m unittest discover -s tests -v
```

122 tests passed locally on macOS. Tests cover original-track preservation, mirror synchronization, speech protection, character evidence, styling, stale sources, busy editor, owned updates, guarded rollback, source mapping and installer safety. [Agent workflow](skills/capcut-cinematic-cards/SKILL.md) · [Commands/plan](skills/capcut-cinematic-cards/references/tool.md) · [Editorial guide](skills/capcut-cinematic-cards/references/editing.md) · [MIT license](LICENSE)
