---
name: capcut-cinematic-cards
description: Use when adding or styling cinematic character introduction cards, time/location cards, THE END cards, and cinema subtitles in a local CapCut project without computer use. Unwraps Compound Clips to map exact scene/shot boundaries, empowers the AI to art-direct bespoke typography and colors per screenplay across all macOS system fonts, places cards in true negative space using calibrated CapCut pixel widths and normalized vertical font metrics, supports simultaneous two-shot character cards, and generates a WYSIWYG frame preview sheet for visual verification.
---

# CapCut Cinematic Cards & Subtitles

Fast, zero-preset, AI-art-directed CapCut title card & subtitle engine (`inspect` -> `probe` -> `apply` + `preview_sheet` verification within a strict **10–20 minute** end-to-end time budget; each CLI command finishes in `< 5 seconds` so it never hangs or drops into background tasks).

## Core Principles (YAGNI — AI Art Direction, Zero Canned Templates, 10–20 Min Budget)

1. **Strict 10–20 Minute End-to-End Time Budget & Anti-Timeout Context Guardrails (Never > 20 Mins, Never Hang)**:
   - Every CLI command (`inspect`, `probe`, `apply`) runs in parallel (`ThreadPoolExecutor`, `< 5s` per command) and prints a **compact summary** (`< 30 lines`) to stdout so `run_command` (`WaitMsBeforeAsync: 10000`) **never** times out into a background task.
   - **Prevent `stream idle timeout (5m0s)` Context Bloat**:
     - **NEVER** load individual `sheet_01..NN.jpg` files — only open the `4x6` (`24`-frame) `batch_sheets` (`probe_batch_01.jpg`, `probe_batch_02.jpg`, ~140KB each) and paginated `preview_pages` (`preview_*_p1.jpg`, `p2.jpg`, `p3.jpg`, ~160KB each), keeping total images loaded across the entire session `<= 6`.
     - **NEVER** dump all 600+ subtitles to stdout or write 600+ `cue_overrides` into `plan.json` — `style_subtitle_track_in_place()` automatically normalizes all cues against the screenplay (`sf-board.json` / `*KICHBAN*.txt`, `normalize_with_screenplay: true`), applies `sentence_case: true` + regex `word_replacements`, and defaults (when the user does not request a custom subtitle style) to the classic **Warm Cinema Yellow Boxless** preset (`Seravek-Medium`, `size: 4.2`, `text_size: 30`, `#E5CE6E`, `y: -0.78`, `stroke_width: 0.028`, `shadow_alpha: 0.82`, `shadow_smoothing: 2.58`, `shadow_distance: 1.8`, `check_flag: 47`). If the user explicitly requests a custom subtitle style, match the user's request.
     - If `subtitle_cue_count == 0` (`subtitle_status: "none_in_draft_do_not_search_other_files"`), **do not** search `mini_draft.json`, `patch.json`, or other projects — simply apply all cards first.
2. **Mandatory Visual Differentiation Across Movies (Zero Test Cloning)**:
   - `cards.py inspect` automatically synthesizes a screenplay-matched `"recommended_style"` across 8 cinema archetypes (`coastal_lifeguard_rescue`, `equestrian_heritage_estate`, `legal_corporate_dynasty`, `military_tactical_thriller`, `high_society_gala_drama`, `rustic_heartland_americana`, `modern_prestige_drama`, etc.) and `cards.py apply` enforces an anti-clone guard so no non-equestrian film can ever reuse the Horse test template (`PlayfairDisplay-Bold` + `CormorantGaramond-BoldItalic` + `#F3CA6E`).
   - Every film MUST have its own distinct visual identity across **4 orthogonal design axes**:
     - **Axis 1 — Genre Font Pairing**: Pick a screenplay-specific pair (`Fraunces-Bold` + `SpaceGrotesk-SemiBold` for smokehouse/heartland/courtroom drama; `BodoniModa-Bold` + `CormorantGaramond-SemiBoldItalic` for luxury/dynasty; `BebasNeue-Regular` + `JetBrainsMono-SemiBold` for military/tactical; `LibreBaskerville-Bold` + `CourierPrime-Bold` for investigative/archive; `InstrumentSerif-Regular` + `PlusJakartaSans-SemiBold` for prestige indie; `PlayfairDisplay-Bold` + `InstrumentSerif-Italic` for Southern estate).
     - **Axis 2 — Case & Tracking (`detail_uppercase`, `detail_letter_spacing`)**: Alternate between tracked uppercase sans/mono kickers (`"detail_uppercase": true, "detail_letter_spacing": 0.05, "detail_size": 3.5`) and mixed-case calligraphic italics (`"detail_uppercase": false, "detail_size": 4.2`).
     - **Axis 3 — Block Alignment (`"align": "outer"` vs `"center"`)**: Use `"align": "outer"` for crisp documentary/A24 lower-thirds (left cards flush-align to `-0.88`, right cards flush-align to `+0.88`) or `"align": "center"` for classical centered-axis symmetry.
     - **Axis 4 — Flankers & World Palette**: Vary flankers (`""` + `"[ ]"`, `"//"` + `"[ ]"`, `"—"` + `"·"`, or `"« »"`) and primary palette (Ember-Copper `#F6A84E` + Terracotta `#E57C44`, Tactical Ice `#C8E0F4`, Antique Brass `#E5C478`, etc.).
3. **Automatic Negative-Space Solver & Glare Avoidance (`< 4.5s` Parallel `apply`)**:
   - `apply` extracts midpoint frames in parallel (`ThreadPoolExecutor`, cached in `/tmp/_capcut_frame_cache`) and runs `score_frame_negative_space()` across all 4 corners (`lower-left`, `lower-right`, `upper-left`, `upper-right`).
   - Supports `"anchor": "auto"` and automatic bright-signage/glare avoidance (`auto_avoid_glare=True` by default: if a lower corner sits over a white sign, white shirt, or glare `p90 >= 202` / `bright_ratio >= 0.24`, it automatically flips to the darker opposite corner).
   - Pass `--no-preview` when only updating subtitles or tweaking text for instant (`< 0.8s`) execution.

## Workflow (4 Steps — Complete End-to-End in <= 10–20 Minutes)

### Step 1: Inspect Timeline & Screenplay Ground Truth (`< 0.5s`)
```bash
python3 "/Users/daho100/Documents/SF Board/.agents/skills/capcut-cinematic-cards/scripts/cards.py" inspect "<project_name_or_path>" --out /tmp/inspect.json
```

### Step 2: Probe Candidate Windows & View Batched Sheets (`< 4s`)
```bash
python3 "/Users/daho100/Documents/SF Board/.agents/skills/capcut-cinematic-cards/scripts/cards.py" probe "<project_name_or_path>" --windows "<recommended_probe_windows>" --out /tmp/probe_out
```
- View the generated `batch_sheets` (`probe_batch_01.jpg`, `probe_batch_02.jpg`, ...) with `read_file` in batch to verify faces, camera cuts, and negative-space anchors.

### Step 3: Author Bespoke `plan.json` & Apply (`< 4.5s` with preview, `< 0.8s` with `--no-preview`)
```bash
python3 "/Users/daho100/Documents/SF Board/.agents/skills/capcut-cinematic-cards/scripts/cards.py" apply "<project_name_or_path>" --plan /tmp/plan.json --preview /tmp/preview.jpg
```

### Step 4: Verify Paginated `preview_pages` (`preview_*_p1.jpg`, ...) with `read_file`
- Inspect the generated `preview_pages` (`16` cards per `4x4` sheet) with `read_file`, adjust any card if needed, and re-run `apply`.

## Reference Guides
- **[references/editing.md](references/editing.md)** — AI art direction guidelines, shot selection, and negative-space composition.
- **[references/subtitle-layout.md](references/subtitle-layout.md)** — In-place subtitle styling tailored per screenplay.
- **[references/tool.md](references/tool.md)** — CLI reference and `plan.json` schema.
