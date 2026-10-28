# Tool reference (for Codex, not manual user work)

Use Python 3.10+. `SCRIPTS` below means this skill's absolute `scripts` directory; resolve it yourself. Paths containing spaces must be quoted safely.

```bash
python3 "$SCRIPTS/cards.py" projects
python3 "$SCRIPTS/cards.py" inspect "PROJECT_PATH"
python3 "$SCRIPTS/cards.py" probe "PROJECT_PATH" --at 120 --before 4 --after 5 --out "FRESH_EVIDENCE_DIR"
python3 "$SCRIPTS/cards.py" stage "PROJECT_PATH" --plan "PLAN.json" --out "FRESH_STAGE_DIR" --font "LOCAL_FONT.ttf"
python3 "$SCRIPTS/cards.py" apply "STAGE_DIR"
python3 "$SCRIPTS/cards.py" verify "STAGE_DIR"
python3 "$SCRIPTS/cards.py" restore "STAGE_DIR"
```

`probe` requires FFmpeg/ffprobe on PATH. It generates source frames every 0.5s plus boundary/cut frames and separate 16kHz audio stems. Read `manifest.json` for the exact timeline time of each frame/stem. It supports affine compound trims and constant speed; reverse, loops, curve speeds or external compounds are flagged. Treat such warnings as unresolved evidence where relevant. It does not render the edited movie. Static image sources use a still frame. Review overlays and transform data separately.

Plan example, wholly fictional (Codex fills actual hashes, absolute paths and findings):

```json
{
  "version": 1,
  "project_sha256": "COPY_FROM_FRESH_INSPECT",
  "style": {"theme": "heritage-drama", "fade_seconds": 0.4},
  "protected_ranges": [
    {"start": 110.0, "end": 115.0, "reason": "Important line and reaction"}
  ],
  "cards": [{
    "id": "mira-intro",
    "kind": "character",
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

Kinds: `time`, `location`, `time-location` (default), `character`. Character evidence requires `character_identity` and `first_appearance`; the helper validates their presence, not their truth. Character cards require a concise established role in `detail`. Omit it only with `evidence.role_omission_reason`, such as an explicit names-only request, unknown role or a spoiler. All evidence findings are the assistant's responsibility. Names and roles must never be guessed merely to pass validation.

Character defaults: name size 6.2, role size 3.8, spacing 0.08/0.12. Heritage drama uses secondary color `#D4CDBE`; other themes retain their secondary palette. When a lower-left character card includes a role and `y` is omitted, the name is placed at -0.64 and role at -0.77. Global/card style and explicit coordinates override these defaults. Time/location defaults are unchanged.

Titles are one line, max 32 characters; detail max 48. Durations 2.8–8s, normally 3.2–3.6. Shorten text instead of shrinking it excessively. Cards cannot overlap each other or declared protected intervals (+150ms buffer). Boundaries are snapped to project fps. Coordinates within ±0.82; detail sits 0.13 below the main line and must remain in bounds. Frame review is still needed for actual text width.

Style keys (global `style`, optionally overridden per card): `theme`, `title_color`, `detail_color` (`#RRGGBB`), `title_size` (3–8), `detail_size` (1.8–4.5), `title_spacing`, `detail_spacing` (0–0.3), `fade_seconds` (0.2–0.8). Native sizes are CapCut units, not points. See `scripts/styles.py` for preset values. One installed font per staged run, chosen with `--font`; without it the tool searches local serif fallbacks.

## Integrity and recovery

The indexed `main_timeline_id` selects the active timeline. The index's project `id` need not equal the timeline's `id`. Root and active main draft must semantically agree. Only existing root/main `draft_info.json`, `.bak` and `template-2.tmp` mirrors are updated; bootstrap `template.tmp`, other timelines and metadata are untouched.

Stages must be outside the project. Each includes exact pre-edit mirrors, previous ownership state, plan, proposed draft, state and a hash manifest. Original tracks/materials must match after removing this tool's owned additions. Fullscreen black, new audio and source edits are never generated. Updates replace only exact ID/hash-owned tracks and text materials; unknown changes stop the operation.

`apply` requires CapCut closed, verifies source/evidence/font/stage hashes even on a repeated apply, locks this tool's writers, writes each mirror atomically, and rolls back its own writes on failure. Mapped media overlapping each evidence window is hashed during staging. Include additional audio, transcript and manifest paths in `evidence.files` to guard those too. Multi-file writes are not one filesystem transaction: a power loss can leave partial mirrors. `restore` accepts known before/after states for recovery; unfamiliar later edits cause refusal. Keep the stage directory private and intact. There is no automatic stale lock removal, editor termination or forced overwrite.

If CapCut was saved after applying, normalization may make ownership hashes differ. Inspect the changes; preserve them. Do not remove ownership guards or blindly reapply old data. If the editor is running, finish staging then report that applying awaits a safely saved/closed editor. Never claim a stage-only run changed the project.
