# CapCut Harness

**One local Codex plugin for cinematic cards, per-source dialogue leveling and freeform requests sent to the same chat.**

[Tiếng Việt](README.md) · [v0.3.0](https://github.com/Ductoii/capcut-cinematic-cards/releases/tag/v0.3.0) · [MIT](LICENSE)

## One-line install

Requires Codex desktop, Python 3.10–3.13 and FFmpeg/ffprobe:

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.3.0/install-harness.py | python3
```

Alternatively, give this repository to local Codex on the computer containing the project and ask it to install v0.3.0, prepare dependencies and open the workspace without Computer Use. No manual JSON editing.

The installer creates a private runtime and registers a local plugin/MCP with the native Codex CLI. Cards and audio share `capcut-harness`. Managed previous installations are backed up. An old service is stopped only when idle and its process belongs to this installation. CapCut is never terminated.

## Open in Codex

Start a **fresh local Codex chat** after installation:

```text
$capcut-harness
Open the workspace for project 1027.
```

The host must support MCP Apps and `ui/message`. The panel includes projects, cards, dialogue leveling, A/B, Apply/Undo and a natural-language request box. Requests go to **the chat hosting that panel**, using its existing Codex tools, without starting a second model. Any host confirmation remains under Codex control.

Examples: “Add only necessary time/location cards at existing black fades”; “Introduce principal characters with verified names and short roles at their first appearance, matching this film”; “Make dialogue consistent between sources while preserving delivery and compound clips.”

Durable requests show saved, sent, acknowledged, working and terminal states. Unconfirmed delivery is marked uncertain and never automatically resent. Other requests are interpreted by Codex according to its available tools; the box has no finite command grammar.

The standalone HTTP UI (`~/.local/bin/capcut-harness`) supports local jobs/listening but has no chat bridge. Open the skill's MCP panel for freeform messages. If tools are missing, ask Codex to repair native registration using `install-harness.py --register-only`. Panel rendering/message support depends on the host version; installation alone does not prove that the host rendered or delivered a message.

## Online-film dialogue preset

Defaults: **−16 LUFS speech anchor, −1.5 dBTP ceiling**, stereo 48 kHz PCM24. This is an online-film starting preset, not a universal film/MV/YouTube certification. A yellow peak meter alone cannot compare perceived loudness across sources.

1. Decode each audible source with supported trim, constant speed, volume and fades.
2. Detect speech per source, optionally conditioning only detector input for very quiet files.
3. Anchor each take with a duration-weighted median loudness and small phrase trims, preserving delivery.
4. Apply gentle RMS compression, 2:1, 15 ms attack/180 ms release, with bounded makeup.
5. Protect source transients, sum the timeline and limit master peaks. Sources without detected speech retain their level and appear in coverage reporting.

Default maximum boost is 48 dB, allowing very quiet material to be lifted while also potentially exposing noise. Separate music/SFX sources do not follow another source's dialogue gain. Background or singing baked into the speech file follows that file; this is not stem separation or speaker identification.

**Level dialogue** prepares a listening job without changing the project. A/B, settings and interval exclusions are available. Excluded intervals restore mapped source audio before summation; the final limiter still applies. Reports expose source coverage and exceptions. No extra full-film validation/listening cycle is run beyond requested work.

Save and close CapCut before Apply. One external root audio master is added; audible original root participants are muted to avoid duplication, while picture, compound structures and cards are preserved. Undo uses exact backups and refuses later foreign edits. Keep `~/.local/share/capcut-harness` for jobs/listening files/backups; long films can use several GB.

## Cinematic cards

- Add time/location cards only when orientation needs them. Prefer existing black fades long enough to read; never stretch a transition to fit text.
- Introduce characters at confirmed first appearances with established names and short roles, without invented identities or spoilers.
- Adapt installed fonts, size, spacing, placement, color and opacity fades to the film.
- Add editable native text on separate root tracks. Preserve compound edits, dialogue, important shots and original transitions. Complex moving titles/glitch effect packs are outside this version.

Codex uses screenplay/caption/frame evidence; this is not guaranteed automatic face recognition. [Card guide](skills/capcut-harness/references/cards.md) · [Plan/commands](skills/capcut-harness/references/tool.md).

## Scope and status

Readable unencrypted local JSON schema `360000`; unknown routing, audible effects and variable speed are refused. Local file tools only, no Computer Use or audio API key. Harness does not upload audio; chat messages/tool context use Codex normally.

v0.3.0 receives syntax/package checks and local plugin installation. The owner opted out of a 300-source or real-film recheck/listening cycle. Historical v0.2.0 [test results](docs/verification.md) do not validate the new engine. Reconstructed source audio is not proof of native CapCut playback/export; reports retain `editor_render_verified: false`. Distortion already in a source cannot be repaired by leveling. macOS is the development environment; other operating systems remain unverified.

[Developer architecture](docs/harness-development.md) · [Decisions](docs/review-and-decisions.md) · [Legacy standalone cards v0.1.1](https://github.com/Ductoii/capcut-cinematic-cards/tree/v0.1.1)
