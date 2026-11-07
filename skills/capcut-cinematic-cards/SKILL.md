---
name: capcut-cinematic-cards
description: Use when adding or styling cinematic character introduction cards, time/location cards, THE END cards, and cinema subtitles in a local CapCut project without computer use. Unwraps Compound Clips to map exact scene/shot boundaries, empowers the AI to art-direct bespoke typography and colors per screenplay across all macOS system fonts, places cards in true negative space using calibrated CapCut pixel widths and normalized vertical font metrics, supports simultaneous two-shot character cards, and generates a WYSIWYG frame preview sheet for visual verification.
---

# CapCut Cinematic Cards & Subtitles

Fast, zero-preset, AI-art-directed CapCut title card & subtitle engine (`inspect` -> `probe` -> `apply` + `preview_sheet` verification in `< 6 seconds`).

## Core Principles (YAGNI — AI Art Direction, Zero Canned Templates)

1. **No Canned Presets & Automatic Google Fonts Fetching**:
   - Do **not** reuse a rigid template across movies. Read the screenplay (`*BANGTRA*.txt`, `sf-board.json`, or `inspect` output) and inspect the actual shots (`probe` contact sheets), then run `cards.py fonts` to pick a bespoke font pairing — either from local macOS fonts OR **any of 1,600+ Google Fonts** (`PlayfairDisplay-Bold`, `Cinzel-Bold`, `CormorantGaramond-BoldItalic`, `BodoniModa-Bold`, `DMSerifDisplay-Regular`, `InstrumentSerif-Italic`, `SpaceGrotesk-SemiBold`, `BebasNeue-Regular`, `Rye-Regular`, etc.). `ensure_capcut_font()` automatically downloads missing Google Fonts, normalizes their vertical metrics (`1.20 * upm`), binds their PostScript name, and installs them into CapCut on the fly.
2. **Expressive Cinema Art Direction (Multi-Span Rich Text, Flankers, Archetype Accents & Stagger)**:
   - **Calligraphic / Genre Font Pairings**: Avoid pairing serif titles with flat corporate UI sans-serifs on drama/period films. Pair a sculptural display/serif title (`PlayfairDisplay-Bold`, `Cinzel-Bold`, `BodoniModa-Bold`, `DMSerifDisplay-Regular`) with a calligraphic/editorial italic (`CormorantGaramond-BoldItalic`, `PlayfairDisplay-BoldItalic`, `InstrumentSerif-Italic`, `LibreBaskerville-Italic`) or a high-character genre display/mono font (`Rye-Regular`, `SpecialElite-Regular`, `JetBrainsMono-SemiBold`, `Syne-Bold`).
   - **Multi-Span Rich Text Contrast (`styles[]`)**: `build_rich_text_content` automatically generates multi-span `styles[]` within a single CapCut text layer — styling honorific prefixes (`Dr. `, `Lt. `, `Judge `, `Sheikh `) and age suffixes (`, 74`) at `0.82–0.85x` size in `accent_color`, highlighting the primary role/status badge (`$5M Champion`, `Stable Hand`, `Head Trainer`) in `detail_accent_color` while keeping the secondary affiliation in `char_detail_color`, and coloring editorial flankers (`—`, `« »`, `·`, `[ ]`) in `flanker_color` at `0.88x` size.
   - **Ornamental Flankers (`flankers`, `scene_flankers`) & Staggered Entrance (`stagger_sec`)**: Wrap detail lines with screenplay-appropriate flankers (`"—"`, `"« »"`, `"·"`, `"[ ]"`, `"//"`) — `format_detail_with_flankers` checks actual font `cmap` glyph coverage so no missing-glyph box ever appears — and stagger the secondary line entrance by `stagger_sec` (`0.10s`).
   - **Character Archetype Palette Accents**: Give antagonists, syndicate figures, or authority roles subtle per-card palette accents (`title_color`, `accent_color`) within the film's color family.
3. **Strict Typographic Hierarchy, Centered-Axis Symmetry & Calibrated Proportions**:
   - **Title (`title_size`: `6.4 .. 7.4`, `scene_title_size`: `6.2 .. 7.2`) vs Detail (`detail_size`: `3.8 .. 4.5`, `scene_detail_size`: `3.8 .. 4.4`)**: Maintain a `1.6:1` to `1.8:1` size ratio (`resolve_style` enforces `detail_size <= 0.65 * title_size`). Scene/location cards are sized boldly on par with character cards so they never look tiny in wide establishing shots.
   - **Normalized Font Metrics (`1.20 * upm`)**: `ensure_capcut_font()` automatically normalizes `hhea` and `OS/2` vertical metrics (`ascent = 0.95 * upm`, `descent = -0.25 * upm`) on every extracted or downloaded `.ttf` so CapCut never shrinks fonts with large ornament boxes (like `HoeflerText-Black` or `CormorantGaramond`) relative to the detail font.
   - **Centered-Axis Symmetry (`align = "center"`, `outer_edge = 0.88`)**: Locks `x_title == x_detail` on the exact same vertical center axis while anchoring the outer edge of the card block at `±0.88`, guaranteeing 100% sub-pixel symmetry in CapCut even when a short name (`Tamarack`) sits above a long role line (`«  $5M Champion · Thoroughbred Stallion  »`).
   - **Trim/Cut-Immune Timing**: `inspect` unwraps split/trimmed Compound Clips with exact `source_timerange` clipping, projects `sf-board.json` shot breakdowns (`goc`) onto surviving timeline segments (`TL x-ys` vs `TRIMMED_OUT`), and `apply` locks both `start_s` (`>= shot_lo + 0.15s`) and `end_s` (`<= shot_hi - 0.08s`) inside a single continuous `scdet` camera sub-shot.
   - **Subtle Cinema Legibility**: Use soft optical drop shadows (`shadow_alpha = 0.90..0.95`, `shadow_smoothing = 0.35..0.45`) with a micro-hairline stroke (`stroke_width = 0.012..0.022`, or `0.0` for pure shadow). Never use thick cartoon borders (`>= 0.04`).
4. **Mandatory WYSIWYG Visual Verification (`preview_sheet`)**:
   - `cards.py apply` automatically renders every applied card onto its actual midpoint video frame at calibrated CapCut pixel scale and saves a contact sheet (`preview_<plan>.jpg`).
   - Always view `preview_<plan>.jpg` with `read_file` immediately after `apply` to confirm contrast, negative space, and hierarchy before finishing.

## Workflow (4 Steps)

### Step 1: Inspect Timeline & Available Fonts (`< 0.5s`)
```bash
python3 "/Users/daho100/Documents/SF Board/.agents/skills/capcut-cinematic-cards/scripts/cards.py" inspect "<project_name_or_path>" --out /tmp/inspect.json
python3 "/Users/daho100/Documents/SF Board/.agents/skills/capcut-cinematic-cards/scripts/cards.py" fonts
```

### Step 2: Probe Candidate Windows for Internal Shot Cuts (`scdet`) & Negative Space (`< 3s`)
```bash
python3 "/Users/daho100/Documents/SF Board/.agents/skills/capcut-cinematic-cards/scripts/cards.py" probe "<project_name_or_path>" \
  --windows "0-35,165-190,347-370,1633-1663" \
  --out /tmp/probe_out
```
- View the generated contact sheets (`sheet_*.jpg`) with `read_file` to pick exact sub-shot `[start_s, end_s]` intervals (`2.5s–4.2s`) and dark/uncluttered negative-space anchors (`lower-left`, `lower-right`, `upper-left`, `upper-right`, `lower-center`).

### Step 3: Author Bespoke `plan.json` & Apply (`< 2s`)
```bash
python3 "/Users/daho100/Documents/SF Board/.agents/skills/capcut-cinematic-cards/scripts/cards.py" apply "<project_name_or_path>" --plan /tmp/plan.json
```

### Step 4: Inspect `preview_sheet` with `read_file`
- Open the `preview_sheet` path returned by `apply` using `read_file`. If any card sits over a bright glare or a background face, flip its `anchor` (`upper-right` <-> `lower-right` / `lower-left`) and re-run `apply`.

## Reference Guides
- **[references/editing.md](references/editing.md)** — AI art direction guidelines, shot selection, and negative-space composition.
- **[references/subtitle-layout.md](references/subtitle-layout.md)** — In-place subtitle styling tailored per screenplay.
- **[references/tool.md](references/tool.md)** — CLI reference and `plan.json` schema.
