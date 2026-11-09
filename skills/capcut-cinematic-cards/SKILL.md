---
name: capcut-cinematic-cards
description: Use when adding or styling cinematic character introduction cards, time/location cards, THE END cards, and cinema subtitles in a local CapCut project without computer use. Unwraps Compound Clips to map exact scene/shot boundaries, empowers the AI to art-direct bespoke typography and colors per screenplay across all macOS system fonts, places cards in true negative space using calibrated CapCut pixel widths and normalized vertical font metrics, supports simultaneous two-shot character cards, and generates a WYSIWYG frame preview sheet for visual verification.
---

# CapCut Cinematic Cards & Subtitles

Fast, screenplay-adaptive CapCut title card & subtitle engine (`inspect` -> `probe` -> `apply` + `preview_pages` verification within a strict **5–15 minute** end-to-end time budget; each CLI command finishes in `< 2 seconds` so it never hangs or drops into background tasks).

## Core Principles (YAGNI — Screenplay-Adaptive Serif Typography, 5–15 Min Budget)

1. **Strict 5–15 Minute End-to-End Time Budget & Anti-Timeout Context Guardrails (Never > 20 Mins, Never Hang)**:
   - Every CLI command (`inspect`, `probe`, `apply`) runs in parallel (`ThreadPoolExecutor`, `< 2s` per command) and prints a **compact summary** (`< 30 lines`) to stdout so `run_command` (`WaitMsBeforeAsync: 10000`) **never** times out into a background task.
   - **High-Craft Compact `inspect.json` (`~800 lines`, 1 `read_file` Call, Zero Quality Loss)**:
     - `inspect` keeps 100% of the screenplay ground truth needed for art direction (`story_scenes` with `scene_name`, `first_clip_shots` `goc` mapped to timeline seconds, and 1-line `kept_segments`; `character_appearances` with full `label`/`desc`, `shot_breakdown` `goc`, `notes`, and `dialogue`) while omitting redundant raw `video_segments` and already-clean subtitles.
     - `inspect` also runs automatic screenplay subtitle normalization and outputs `"subtitle_review_candidates"`: a compact list of ONLY the subtitle cues that still have any out-of-screenplay word paired side-by-side with `"screenplay_dialogue"`, so you can add exact `"cue_overrides"` in `plan.json` without reading 600+ clean cues.
     - `probe` extracts sub-shot frames in `< 1s` and builds ONLY `4x6` (`24`-frame) `probe_batch_01..NN.jpg` sheets (zero individual `sheet_*.jpg` clutter).
   - **Prevent `stream idle timeout (5m0s)` Context Bloat**:
     - **ONLY** open `batch_sheets` (`probe_batch_01.jpg`, `probe_batch_02.jpg`, ...) and paginated `preview_pages` (`preview_*_p1.jpg`, `p2.jpg`, `p3.jpg`), keeping total images loaded across the entire session `<= 6`.
     - **NEVER** dump all 600+ subtitles to stdout or write 600+ `cue_overrides` into `plan.json` — `style_subtitle_track_in_place()` automatically normalizes all cues against the screenplay (`sf-board.json` / `*KICHBAN*.txt`, `normalize_with_screenplay: true`), applies `sentence_case: true` + regex `word_replacements`, and defaults (when the user does not request a custom subtitle style) to the classic **Warm Cinema Yellow Boxless** preset (`Seravek-Medium`, `size: 4.2`, `text_size: 30`, `#E5CE6E`, `y: -0.78`, `stroke_width: 0.028`, `shadow_alpha: 0.82`, `shadow_smoothing: 2.58`, `shadow_distance: 1.8`, `check_flag: 47`). If the user explicitly requests a custom subtitle style, match the user's request.
     - If `subtitle_cue_count == 0` (`subtitle_status: "none_in_draft_do_not_search_other_files"`), **do not** search `mini_draft.json`, `patch.json`, or other projects — simply apply all cards first.
2. **Screenplay-Adaptive Serif Typography, Full Detail Size (`5.0`), & Centered-Axis Symmetry (`x_title == x_detail`)**:
   - `cards.py inspect` synthesizes `"recommended_style"` from 7 screenplay world archetypes using **World-Matched Serif Titles + Mixed-Case Calligraphic Italic Serif Details (`detail_size: 5.0`, `scene_detail_size: 5.0`, `detail_uppercase: false`)** and **100% Centered-Axis Symmetry (`align: "center"`, `x_title == x_detail`)**:
     - **`rustic_heartland_americana` (BBQ / Smokehouse / County Fair / Heartland)**: `Fraunces-Bold` (character title) + `Bitter-Bold` (scene title) + `Lora-BoldItalic` (detail `size: 5.0`), Hickory Amber `#F5B85C` + Smoked Cream `#FAF3E6` + Honey Gold `#FFD485`, flankers `"—"` / `"•"`.
     - **`coastal_lifeguard_rescue` (Ocean / Lifeguard / Marina)**: `Cinzel-Bold` + `Optima-ExtraBlack` + `Lora-BoldItalic` (`size: 5.0`), Sunlit Gold `#F4C86A` + Seafoam `#EBF7FA` + Surf Cyan `#9BE2F2`, flankers `"~"` / `"•"`.
     - **`equestrian_heritage_estate` (Stallion / Thoroughbred / Southern Estate)**: `PlayfairDisplay-Bold` + `CormorantGaramond-BoldItalic` (auto optical-boosted `1.14x`) + `Cinzel-Bold`, Heritage Gold `#F3CA6E` + Warm Parchment `#F6EFE2`, flankers `"—"` / `"·"`.
     - **`legal_corporate_dynasty` (Courtroom / Boardroom / Hospital / Dynasty)**: `BodoniModa-Bold` + `Didot-Bold` + `PlayfairDisplay-BoldItalic` (`size: 5.0`), Champagne Brass `#EED484` + Crisp Alabaster `#F2F5F8`, flankers `"—"` / `"◇"`.
     - **`military_tactical_thriller` (Military / Aviation / Precinct / Federal)**: `Copperplate-Bold` + `Cinzel-Bold` + `Optima-Bold` (`size: 5.0`), Platinum Silver `#EBF0F5` + Tactical Amber `#F2C45A`, flankers `"—"` / `"•"`.
     - **`high_society_gala_drama` (Gala / Symphony / Conservatory / Auction)**: `DMSerifDisplay-Regular` + `BodoniModa-Bold` + `PlayfairDisplay-BoldItalic` (`size: 5.0`), Rose Champagne `#F5D38C` + Velvet Ivory `#FAF5FF`, flankers `"« »"` / `"◇"`.
     - **`modern_prestige_drama` (Default Contemporary Drama)**: `LibreBaskerville-Bold` + `Lora-BoldItalic` (`size: 5.0`), Warm Cinema Gold `#F2CC76` + Alabaster `#F5F2EB`, flankers `"—"` / `"•"`.
   - **Never** use tiny ALL-CAPS sans-serif (`SpaceGrotesk-SemiBold` + `detail_uppercase: true`), square brackets `[ ]`, or mismatched `x_title != x_detail` offsets.
3. **Automatic Negative-Space Solver & Glare Avoidance (`< 2s` Parallel `apply`)**:
   - `apply` shares cached frames in `/tmp/_capcut_frame_cache` with `probe` and scores all 4 corners (`lower-left`, `lower-right`, `upper-left`, `upper-right`), automatically flipping away from white signage, white shirts, or bright glare (`auto_avoid_glare=True`).
   - Pass `--no-preview` when only updating subtitles or tweaking text for instant (`< 0.5s`) execution.

## Workflow (4 Steps — Complete End-to-End in <= 5–15 Minutes on Any Machine)

> Run `<skill_dir>/scripts/cards.py` using the path where this `SKILL.md` is located.

### Step 1: Inspect Timeline & Auto-Generate Starter Plan (`< 0.5s`)
```bash
python3 "<skill_dir>/scripts/cards.py" inspect "<project_name_or_path>" --out /tmp/inspect.json
```
- Writes compact `/tmp/inspect.json` AND pre-populates `/tmp/plan_<project>.json` (`/tmp/starter_plan_<project>.json`).

### Step 2: Probe Candidate Windows & Score Negative-Space Anchors (`< 1s`)
```bash
python3 "<skill_dir>/scripts/cards.py" probe "<project_name_or_path>" --windows "<recommended_probe_windows>" --out /tmp/probe_out
```
- View `probe_batch_01.jpg`, `probe_batch_02.jpg`, ... with `read_file` in batch to verify faces and sub-shot timings, then refine `/tmp/plan_<project>.json` (titles, details, simultaneous two-shot cards, or sub-shot windows).

### Step 3: Apply `/tmp/plan_<project>.json` (`< 2s` with preview, `< 0.5s` with `--no-preview`)
```bash
python3 "<skill_dir>/scripts/cards.py" apply "<project_name_or_path>" --plan "/tmp/plan_<project>.json" --preview /tmp/preview.jpg
```

### Step 4: Verify Paginated `preview_pages` (`preview_*_p1.jpg`, ...) with `read_file`
- Inspect the generated `preview_pages` (`16` cards per `4x4` sheet) with `read_file`, adjust any card if needed, and re-run `apply`.

## Reference Guides
- **[references/editing.md](references/editing.md)** — AI art direction guidelines, shot selection, and negative-space composition.
- **[references/subtitle-layout.md](references/subtitle-layout.md)** — In-place subtitle styling tailored per screenplay.
- **[references/tool.md](references/tool.md)** — CLI reference and `plan.json` schema.
