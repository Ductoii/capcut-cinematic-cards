# Tool reference (for Codex, not manual user work)

Use Python 3.10+. `SCRIPTS` below means this skill's absolute `scripts` directory; resolve it yourself. Paths containing spaces must be quoted safely.

```bash
python3 "$SCRIPTS/cards.py" projects
python3 "$SCRIPTS/cards.py" inspect "PROJECT_PATH"
python3 "$SCRIPTS/cards.py" probe "PROJECT_PATH" --at 120 --before 4 --after 5 --out "FRESH_EVIDENCE_DIR"
python3 "$SCRIPTS/cards.py" stage "PROJECT_PATH" --plan "PLAN.json" --out "FRESH_STAGE_DIR" --font "LOCAL_FONT.ttf"
python3 "$SCRIPTS/cards.py" restyle "PROJECT_PATH" --plan "REVIEWED_PLAN.json" --out "FRESH_STAGE_DIR"
python3 "$SCRIPTS/cards.py" apply "STAGE_DIR"
python3 "$SCRIPTS/cards.py" verify "STAGE_DIR"
python3 "$SCRIPTS/cards.py" restore "STAGE_DIR"
```

`probe` requires FFmpeg/ffprobe on PATH. It generates source frames every 0.5s plus boundary/cut frames and separate 16kHz audio stems. Read `manifest.json` for each frame/stem's timeline time. A boundary inside the last video frame records the actual packet PTS and `requested_source_time`. A sub-frame audio/container overhang is explicitly marked `sample_policy: last_available_video_frame` with a warning; a longer bad trim is rejected. No source media is changed. The last available frame does not prove native holding, black or silence. It supports affine compound trims and constant speed; reverse, loops, curve speeds or external compounds are flagged. It does not render the edited movie. Static images use a still frame. Review overlays and transforms separately.

Plan example, wholly fictional (Codex fills actual hashes, absolute paths and findings):

```json
{
  "version": 1,
  "project_sha256": "COPY_FROM_FRESH_INSPECT",
  "style": {"theme": "heritage-drama", "fade_seconds": 0.4},
  "introduce_characters": true,
  "character_review": [
    {"id": "mira", "name": "Mira Vale", "status": "introduced", "card_id": "mira-intro"},
    {"id": "leo", "name": "Leo Vale", "status": "omitted", "reason": "Identity is deliberately hidden in the reviewed scene."}
  ],
  "protected_ranges": [
    {"start": 110.0, "end": 115.0, "reason": "Important line and reaction"}
  ],
  "cards": [{
    "id": "mira-intro",
    "kind": "character",
    "characters": ["mira"],
    "title": "Mira Vale",
    "detail": "Restorer",
    "start": 120.5,
    "duration": 3.4,
    "layout": "lower-left",
    "x": -0.52,
    "y": -0.64,
    "evidence": {
      "start": 116,
      "end": 127,
      "frames": ["ABSOLUTE_REVIEW_FRAME.jpg"],
      "visual_review": "Reviewed the whole hold; free lower left, no face/hand/subtitle collision.",
      "dialogue_review": "Reviewed all audible stems at their global offsets and the timed transcript.",
      "character_identity": "Matched screenplay scene and supplied character portrait.",
      "first_appearance": "Reviewed earlier scene metadata and relevant frames; first recognizable appearance."
    }
  }]
}
```

Kinds: `time`, `location`, `time-location` (default), `character`, `ending`. Character evidence requires `character_identity` and `first_appearance`; the helper validates presence, not truth. Character cards require a concise established role in `detail`; omit only with `evidence.role_omission_reason`. With `introduce_characters: true`, every declared principal needs a `character_review` entry: `introduced` links to a character card listing that person's ID, or `omitted` records a concrete reason. A pair shares one card and lists both IDs; each principal is introduced once. Legacy plans without this flag/ledger remain readable. Codex must actually read the cast and account for everyone requested, not invent identities or an omission to pass validation.

Character defaults: name size 6.2, role size 3.8, spacing 0.08/0.12. Heritage drama uses secondary color `#D4CDBE`; other themes retain their secondary palette. When a lower-left character card includes a role and `y` is omitted, the name is placed at -0.64 and role at -0.77. Global/card style and explicit coordinates override these defaults. Time/location defaults are unchanged.

Titles permit up to two nonempty lines, max 96 characters; detail max 128. Keep labels concise and review reading time. Durations 2.8–8s, normally 3.2–3.6. Shorten text instead of shrinking it excessively. Cards cannot overlap each other or declared protected intervals (+150ms buffer). Boundaries are snapped to project fps. Coordinates within ±0.82; detail sits 0.13 below the main line and must remain in bounds. Frame review is still needed for actual text width.

Style keys (global `style`, optionally overridden per card): `theme`, `title_color`, `detail_color` (`#RRGGBB`), `title_size` (3–8), `detail_size` (1.8–4.5), `title_spacing`, `detail_spacing` (0–0.3), `fade_seconds` (0.2–0.8). Native sizes are CapCut units, not points. See `scripts/styles.py` for preset values. Choose an installed font with `--font`, root `font`, or per-card `font` (most specific wins). Initial cards without a choice use a local fallback; restyles preserve existing fonts unless explicitly overridden.

`fade_seconds` creates opacity keyframes, not a CapCut animation-tab entry. To reuse a **confirmed existing local native entry animation**, add this root option with actual IDs/paths read from the current draft:

```json
"native_fade_in": {
  "material_id": "EXISTING_ANIMATION_MATERIAL_ID",
  "source_segment_id": "EXISTING_TEXT_SEGMENT_ID",
  "review": "Reviewed the existing native fade-in on this text and its local resource.",
  "files": ["ABSOLUTE_EXISTING_EFFECT/config.json", "ABSOLUTE_EXISTING_EFFECT/studioAnim.lsanim"]
}
```

The material must already be referenced by that text segment and contain one `in` animation. Listed resources must stay within its existing local resource directory and are hashed. It is reused on title and detail together; the original animation object is unchanged. A different existing text animation is refused rather than replaced. No effect is downloaded or invented. Native playback is still not verified by staging.

## Restyling a saved project

`stage` retains its exact ownership guard. If CapCut saved normalized defaults or a user changed a title, do not update the ownership file first or force a rerun. `inspect` now returns `ownership`: status, changed/missing IDs and current hashes. Compare the current owned objects with the previous stage's `draft.json`. For changed owned objects, copy the fresh `project_sha256`, `state_sha256`, `tracks` and `materials` from that report into root `ownership_review`, then add a nonempty `findings` describing the actual reviewed changes.

Run `restyle` with that fresh plan. It requires all known owned IDs to remain, rejects stale/incomplete reviews, stages backups without project writes, and keeps current wording, timing, positions, keyframes, effects and saved defaults. Only explicitly requested typography fields change by default; `replace_text: true` on a card explicitly permits a wording/case change (complex rich-text replacement is refused). Timing/layout from an older plan are not restored. New reviewed cards may be added; owned cards omitted from the plan remain, and new cards cannot overlap them. Unowned additions, including user text and animation materials, stay intact. `apply`, `verify` and guarded `restore` use the same transaction checks as ordinary staging.

For scene-change timing, Codex should record the original cut/fade anchor and why a later hold was necessary in evidence findings. The tool does not infer that an entire transition is opaque black or automatically choose timestamps. For an ending card use `kind: ending`, a safe existing final hold and the same evidence workflow; it never appends time or black.

## Integrity and recovery

The indexed `main_timeline_id` selects the active timeline. The index's project `id` need not equal the timeline's `id`. Root and active main draft must semantically agree. By default, only existing root/main `draft_info.json`, `.bak` and `template-2.tmp` mirrors are updated (the explicit incremental snapshot option is described below); bootstrap `template.tmp`, other timelines and metadata are untouched.

Stages must be outside the project. Each includes exact pre-edit mirrors, previous ownership state, plan, proposed draft, state and a hash manifest. Original tracks/materials must match after removing this tool's owned additions. Fullscreen black, new audio and source edits are never generated. Updates replace only exact ID/hash-owned tracks and text materials; unknown changes stop the operation.

`apply` requires CapCut closed, verifies source/evidence/font/stage hashes even on a repeated apply, locks this tool's writers, writes each mirror atomically, and rolls back its own writes on failure. Mapped media overlapping each evidence window is hashed during staging. Include additional audio, transcript and manifest paths in `evidence.files` to guard those too. Multi-file writes are not one filesystem transaction: a power loss can leave partial mirrors. `restore` accepts known before/after states for recovery; unfamiliar later edits cause refusal. Keep the stage directory private and intact. There is no automatic stale lock removal, editor termination or forced overwrite.

If CapCut was saved after applying, normalization may make ownership hashes differ. Inspect the changes; preserve them. Do not remove ownership guards or blindly reapply old data. If the editor is running, finish staging then report that applying awaits a safely saved/closed editor. Never claim a stage-only run changed the project.

On macOS, closing the project/window can leave the main CapCut process alive. After the stage is ready, ask for **Save, then Quit CapCut (Cmd+Q)** when apply reports it running. Never kill the editor or bypass that check. A safe quit may save again; if it does, refresh inspection/review and create a fresh stage.


## Reviewed simultaneous introductions and layout repairs

Two independent character labels may share an interval only with the same `simultaneous_group`. Each lists exactly one distinct principal in `characters`, links through `character_review` with `introduce_characters: true`, and supplies `bounds`, `evidence.layout_review` and `evidence.identity_association`. All members share frame-quantized start/end and fade duration. Bounds cover the full name/role pair through the hold and may not overlap each other or declared `exclusion_zones`. Every overlapping pair is checked, including a third card nested inside a longer interval. Independent tracks retain editable clips. A group is not permission to cover faces or subtitles.

Example additions to each of two otherwise complete, evidence-backed character cards:

```json
{"simultaneous_group":"entrance-pair", "characters":["mira"],
 "x":-0.5,"y":0.4,"bounds":[-0.8,0.15,-0.2,0.55],
 "exclusion_zones":[[-0.85,-0.85,0.85,-0.6]],
 "evidence":{"layout_review":"Actual full-hold frames and subtitle background reviewed.",
             "identity_association":"Mira remains on the left beside this label throughout."}}
```

The other label uses its own principal and spatially separated bounds. Frame paths and the normal identity/first-appearance evidence are still required. A protected range marked `kind: dialogue` permits small character identifiers during speech; an untyped protected range or a reveal/action remains protected. Do not mark all dialogue as an important reaction just to defer introductions.

A per-card `text_layout` can explicitly set `scale` (0.1–4), `line_max_width` (0.05–0.9), `fixed_width` (positive native units), and `title_x`, `title_y`, `detail_x`, `detail_y` (−0.82–0.82). Position repairs require reviewed bounds and layout findings. Scale updates both native scale representations together. Typography updates synchronize existing `content`/`base_content`, preserve unrelated rich-text properties, and change only requested size, spacing, color or font fields. `replace_text: true` permits deliberate line breaks/wording changes. Restyles retain short manually saved holds rather than stretching them to a default reading duration.

For a known native incremental snapshot, root `sync_incremental_snapshot: true` synchronizes only the content of existing owned text segments in `Timelines/<main>/attachment/patch/mini_draft.json`, preserving unrelated snapshot data. It requires an empty `patch.json` and exact correspondence to current card content; it refuses pending edits, missing IDs or structural additions. It never clears patches or replaces the snapshot with a full draft. Both the snapshot and patch are guarded through apply; the snapshot has a reversible transaction backup. Without this option incremental files are untouched. Other snapshot schemas are not supported.
