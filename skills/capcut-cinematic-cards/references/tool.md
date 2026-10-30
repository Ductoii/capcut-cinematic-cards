# Tool reference (for Codex, not manual user work)

Use Python 3.10+. `SCRIPTS` below means this skill's absolute `scripts` directory; resolve it yourself. Paths containing spaces must be quoted safely.

```bash
python3 "$SCRIPTS/cards.py" projects
python3 "$SCRIPTS/cards.py" inspect "PROJECT_PATH"
python3 "$SCRIPTS/cards.py" probe "PROJECT_PATH" --at 120 --before 4 --after 5 --out "FRESH_EVIDENCE_DIR"
python3 "$SCRIPTS/cards.py" stage "PROJECT_PATH" --plan "PLAN.json" --out "FRESH_STAGE_DIR" --font "LOCAL_FONT.ttf"
python3 "$SCRIPTS/cards.py" restyle "PROJECT_PATH" --plan "REVIEWED_PLAN.json" --out "FRESH_STAGE_DIR"
python3 "$SCRIPTS/cards.py" review "STAGE_DIR" --out "FRESH_REVIEW_DIR"
python3 "$SCRIPTS/cards.py" preview "STAGE_DIR" --calibration "PRIVATE_OBSERVATIONS.json" --out "FRESH_PREVIEW_DIR"
python3 "$SCRIPTS/cards.py" apply "STAGE_DIR" --review "INDEPENDENT_VERDICT.json"
python3 "$SCRIPTS/cards.py" verify "STAGE_DIR"
python3 "$SCRIPTS/cards.py" restore "STAGE_DIR"
```

`probe` requires FFmpeg/ffprobe on PATH. It generates source frames every 0.5s plus boundary/cut frames and separate 16kHz audio stems. Read `manifest.json` for each frame/stem's timeline time. For footage, `timeline_time` is the requested snapshot instant and `source_time` is the actual presentation PTS active then, chosen at or before the mapped source instant. When different, `requested_source_time` retains that original instant; accurate seeking must not show a future shot. A sub-frame audio/container overhang is explicitly marked `sample_policy: last_available_video_frame` with a warning; a longer bad trim is rejected. No source media is changed. The last available frame does not prove native holding, black or silence. It supports affine compound trims and constant speed for media with a zero container timestamp origin; nonzero origins, reverse, loops, curve speeds or external compounds are refused/flagged rather than guessed. It does not render the edited movie. Static images use a still frame. Review overlays and transforms separately.

Plan example, wholly fictional (Codex fills actual hashes, absolute paths and findings):

```json
{
  "version": 2,
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
    "bounds": [-0.8, -0.8, -0.1, -0.4],
    "evidence": {
      "start": 116,
      "end": 127,
      "manifest": "ABSOLUTE_PROBE_DIR/manifest.json",
      "frames": ["ALL_SELECTED_FULL_HOLD_FRAME_PATHS_FROM_MANIFEST"],
      "layout_review": "Both line anchors and actual glyph extents reviewed through the hold.",
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

Titles permit up to two nonempty lines, max 96 characters; detail max 128. Keep labels concise and review reading time. Character durations normally 2–8s; other cards 2.8–8s, normally 3.2–3.6. A version2 card below its normal minimum (2s for characters, 2.8s for other kinds) needs a specific `evidence.short_hold_review` explaining concise wording, actual safe scene/shot and reading time. The helper requires enough frames for distinct opacity keyframes and, when native fades are attached, known positive effect durations whose sum is shorter than the hold. These technical conditions do not establish readability; independent `reading_time_passed` remains required. Legacy new-plan minimums are unchanged. A short character identifier can end before a cut instead of surviving into another person’s shot. A time/location label can stay within its actual scene instead of starting over an unrelated preceding scene to reach 2.8s. Shorten text instead of shrinking it excessively. Cards cannot overlap each other or declared protected intervals (+150ms buffer). Boundaries are snapped to project fps. Coordinates within ±0.82; detail sits 0.13 below the main line and must remain in bounds. Frame review is still needed for actual text width.

Style keys (global `style`, optionally overridden per card): `theme`, `title_color`, `detail_color` (`#RRGGBB`), `title_size` (3–8), `detail_size` (1.8–4.5), `title_spacing`, `detail_spacing` (0–0.3), `fade_seconds` (0.2–0.8). Native sizes are CapCut units, not points. See `scripts/styles.py` for preset values. Choose an installed font with `--font`, root `font`, or per-card `font` (most specific wins). Initial cards without a choice use a local fallback; restyles preserve existing fonts unless explicitly overridden.

For new cards matching a reviewed paired native appearance, root `card_appearance` accepts:

```json
"card_appearance": {
  "path": "/absolute/private/approved-appearance.json",
  "sha256": "EXACT_FILE_SHA256",
  "review": "Both title/detail appearance and stored scales reviewed against the approved example."
}
```

The local JSON uses `version: 1` and `layers.title` / `layers.detail`. Each layer contains native `appearance` fields, one-style `rich_content_example`, `clip_scale: {"x": ..., "y": ...}` and `uniform_scale: {"on": ..., "value": ...}`. Codex prepares this from the supplied native example; users do not edit JSON. The helper copies reviewed typography/shadow/background metadata and each scale independently, generates new wording/ranges/IDs/timing/positions and attaches the requested fade separately. The JSON and used font binaries are pinned through apply. It never copies tracks, identities, timing, positions or recognition data from an appearance source.

This option is for new cards, not `restyle` / `preserve_owned`. To avoid silently ignored settings, omit CLI/root/card font overrides and all global/card style keys except `fade_seconds`; `text_layout.scale` also conflicts. Reviewed position and width options remain available. Without `card_appearance`, existing theme/font behavior is unchanged. Private appearance files and fonts do not belong in the public repo.

`fade_seconds` creates opacity keyframes, not a CapCut animation-tab entry. To reuse a **confirmed existing local native entry animation**, add this root option with actual IDs/paths read from the current draft:

```json
"native_fade_in": {
  "material_id": "EXISTING_ANIMATION_MATERIAL_ID",
  "source_segment_id": "EXISTING_TEXT_SEGMENT_ID",
  "review": "Reviewed the existing native fade-in on this text and its local resource.",
  "files": ["ABSOLUTE_EXISTING_EFFECT/config.json", "ABSOLUTE_EXISTING_EFFECT/studioAnim.lsanim"]
}
```

The material must already be referenced by that text segment and contain one `in` animation or an existing `in`/`out` pair. Listed resources must stay within the existing resource directories, include files from both directions when paired, and are hashed. It is reused on title and detail together; the original animation object is unchanged. A different existing text animation is refused rather than replaced. No effect is downloaded or invented. Native playback is still not verified by staging. To import that reviewed native material from another local project, also supply `source_project` and its fresh `source_project_sha256`. Only the imported material is owned by the transaction; the source project is read-only. Apply/restore refuse if an unrelated user segment later shares an owned imported animation that would be removed.

When the template's timing consumes a brief hold, optional `durations_seconds`, for example `{"in": 0.2, "out": 0.2}`, changes only the named existing directions on a separate owned copy. Unspecified directions retain their original duration; effect resources, IDs and other animation settings are preserved. Durations must be positive and their total must leave a plateau on every new card. Include the timing decision in `review`, align opacity-keyframe `fade_seconds`, and judge the complete reading event independently; a shorter fade alone does not make a short label readable. Omitting this option preserves existing behavior and template timing.

Whenever a native fade is explicitly attached, all card holds require known positive native durations and a remaining plateau, including ordinary holds and restyles. Unknown template durations are refused; omitting the timing override does not skip this check.

## Full-hold evidence and job requirements

Use plan version2 for new work. Each card requires `bounds`, `evidence.layout_review`, and the absolute `evidence.manifest` returned by `probe`. The manifest must match the current project revision. Select all footage frames spanning the complete hold at the probe’s half-second cadence, including the end and cut-adjacent frames; opening portraits and static overlay/logo frames cannot cover a later moving-footage interval. Manifest and selected frames are pinned through apply. Version1 remains readable for existing plans.

Probe adds heuristic internal scene cuts and timeline source boundaries to `manifest.cuts`; FFmpeg scene detection can miss or falsely detect a change. Visually inspect all frames. A character hold crossing any reported cut needs one `evidence.cut_continuity` item:

```json
{"at": 121.7, "characters": ["mira"],
 "before": "SELECTED_FRAME_IMMEDIATELY_BEFORE.jpg",
 "after": "SELECTED_FRAME_IMMEDIATELY_AFTER.jpg",
 "review": "Same confirmed principal remains identifiable on both sides; label stays associated."}
```

Both frames must belong to this manifest, be selected, and fall within0.15s on their respective side. Otherwise end before the cut. These checks validate evidence consistency, not identity recognition or native glyph geometry.

Record actual job obligations in root `requirements`, e.g. `{"ending": true, "native_fade": true}`. An ending requirement requires `kind: ending`; native fade requires the reviewed option above, not opacity keyframes alone. Do not infer an ending for every film.

For an authorized subtitle appearance change, root `subtitle_template` accepts `source_project`, `source_project_sha256`, `material_id`, nonempty `review`, optional native `y` and optional integer `wrap_columns` (8–120). Choose an actual single-style native subtitle from a reviewed local project. It copies appearance and pins fonts/source while preserving words and cue timing; balanced two-line wrapping refuses overflow rather than deleting words. See [subtitle layout](subtitle-layout.md). No PNG captions or private writer is needed.

## Independent source review before applying new plans

`review STAGE --out FRESH_DIR` compiles neutral facts from the staged native draft, not author conclusions: actual text/positions and every footage frame inside or within0.15s of each hold in its pinned probe. Intermediate unselected probe frames are included. The helper reconstructs static uniform zoom/pan through same-aspect nested canvases before drawing the yellow declared card rectangle. Cyan rectangles mark static image extents; they do not recreate masking, alpha or native compositing. `facts.static_overlays` records their actual time ranges and geometry. Unsupported rotation/flip, animated geometry, material crops, aspect changes or exposed canvas backgrounds are refused by this source-review path; preserve the user's picture and obtain separate native evidence rather than treating the raw frame as equivalent.

Read `bundle.pages[*].frames` in image order for exact source/time and `inside_hold`; use corresponding `display_frames` for full-size reconstructed geometry and the raw frame paths for source identity evidence. Display images and pages are hash-pinned. This is not a native typography/effects renderer and cannot prove glyph width, subtitle wrapping/background or fades.

Each display frame includes a footer **outside the complete picture**, showing its frame index, film/source time, card interval/context status and color legend. Outside the card interval, the yellow card declaration is hidden; those are context frames, not a card carried onto the next person. Cyan is an image overlay such as a logo, never the detail text line. Read both text-line positions from the staged facts. `display_geometry` records the picture dimensions and footer height; the footer is not video content. Labels use a small built-in bitmap font, with no optional FFmpeg text filter or font dependency.

A still-image hold can supply review frames when no moving footage is active at those times. Its known static extent must cover the canvas; the helper reconstructs the viewport without stretching the image. Partial images that expose an unresolved canvas background require separate native evidence. A static logo over active footage never replaces the footage observations. Source dimensions must be positive and known even for unit transforms; missing dimensions are unsupported rather than assumed to match the canvas.

`inside_hold: false` only places that sample before/after the card interval. It does not identify a scene cut, a new person or the next card. For decisive checks, open one full-size image per call and record its exact filename/time/flag and actual visible subjects before proceeding.

A new independent reviewer receives the bundle, raw reference/cast/production materials and brief, without the author's review prose. Every frame needs its own actual observation. Reviewer writes a JSON file with this structure (repeat every card/frame from `bundle.facts`):

```json
{
  "version": 1,
  "independent": true,
  "reviewer": "ACTUAL_SEPARATE_REVIEWER",
  "bundle": "ABSOLUTE_REVIEW_DIR/bundle.json",
  "bundle_sha256": "SHA256_OF_BUNDLE_FILE",
  "native_render_verified": false,
  "cards": [{
    "id": "mira-intro",
    "reading_time_passed": true,
    "reading_time_review": "Actual hold and both lines reviewed for reading.",
    "first_appearance_passed": true,
    "first_appearance_review": "Earlier raw entrances and the relevant source version checked.",
    "frames": [{
      "file": "EXACT_FRAME_PATH_FROM_BUNDLE",
      "observation": "Describe who actually appears and where the rectangle lies.",
      "subjects": ["mira"],
      "associated_characters": ["mira"],
      "layout_passed": true
    }]
  }]
}
```

For non-character cards use `necessity_review` and `necessity_passed` instead of the first-appearance fields. Pass flags must reflect the actual judgment: missing or false reading-time, first-entrance or necessity flags block apply, even with nonempty prose. For a wrong person record that actual ID and `layout_passed: false`; do not copy expected IDs to satisfy validation. A name near another person fails even if its expected person remains elsewhere in the shot. Outside-hold context frames still receive observations; active identity/layout gates use inside-hold frames. `apply --review` checks every card/frame, expected identity AND spatial association, layout verdict, complete unchanged bundle/pages and staged draft/plan hashes. The flag `independent` is a declaration, not cryptographic proof of a separate model: the orchestrator must actually dispatch a separate reviewer and retain the image-view evidence. The author cannot self-certify.

Version2 requires this verdict; legacy version1 transactions remain readable. Do not downgrade a new task to bypass review. Source review cannot assert native rendering, so this verdict keeps `native_render_verified: false`. Applying a source-reviewed candidate is not native visual acceptance; native output must still be examined before completion claims.

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


## Calibrated visible-text preview

`preview` is an optional local reconstruction for judging letters over the actual moving footage. It needs Pillow as well as FFmpeg/ffprobe; other commands remain independent of Pillow. Codex prepares the private calibration, runs the command and opens the resulting movie/whole-hold sheets. Do not ask the user to edit calibration JSON. A neutral `review` sheet only shows declarations, so it cannot establish glyph containment.

Calibration schema: `version: 1`, `canvas: {width, height}` in the observed preview/reference space, and `entries`. Each entry has `class` (`title`, `detail`, `subtitle`, or `text`), absolute `font_path`, `font_sha256`, exact native `font_size`, `clip_scale: {x, y}`, `letter_spacing`, observed `observed_font_px`, `tracking_px`, `line_gap_px`, and an `observation` naming the evidence and uncertainty. Match every used typography class exactly. Keep font files, frames, calibration values and private paths outside the public package.

Use known rendered words in the same font/style to constrain the visible footprint; cross-check another word and the paired detail line. Pixel size and tracking are observed for that one style, not a conversion formula for all CapCut text. Native uniform-scale precedence, kerning, rich shadows, automatic wrap and extra native effects may remain unknown. Missing/mismatched calibration must stop the command rather than using a generic small font. Overflow is a finding; never auto-shrink text to hide it.

The output manifest pins the source/calibration and labels reconstruction limits with `native_render_verified: false`. View the actual letters on all card holds, cut-adjacent frames, longest one/two-line subtitles, and first/last fade samples. Include these preview artifacts with the neutral bundle for independent review; source rectangles alone do not meet this typography check. A local reconstruction does not certify native playback or exact subtitle backgrounds. When the user chooses preview instead of an export, deliver the preview and state the remaining difference without repeatedly requesting a full-film export.


When one specific subtitle cue covers a reviewed action, optional `subtitle_template.cue_positions` contains `{segment_id, x and/or y, review}` entries (optionally `wrap_columns` for that cue only). Use exact current subtitle segment IDs and a whole-cue visual reason. Coordinates stay within the reviewed canvas; unknown/duplicate IDs and ambiguous source matches are refused. Linked cues sharing a subtitle material must use one effective wrap width; conflicting per-cue wrapping is refused rather than silently changing another cue. Position overrides remain per segment. This only overrides those cues after applying the default subtitle band; words, timing, metadata, other cues and typography are retained. The preview includes each explicitly repositioned cue through its full end, even if the accompanying card ends sooner. Do not change all captions to solve one local handoff/gesture collision.
