# AI Art Direction, Typography, Timing & Composition Guide

## 1. Screenplay-Adaptive Cinema Art Direction System

Every film has its own world, lighting regime, and dramatic tension. `cards.py inspect` automatically analyzes `sf-board.json` and synthesizes `"recommended_style"` across **5 pillars**:

### Pillar A: World-Matched Serif + Italic Serif Archetypes
All 7 screenplay archetypes use high-craft Serif Titles (`6.8` character / `6.6` scene) paired with Mixed-Case Calligraphic Italic Serif Details (`detail_size: 5.0`, `scene_detail_size: 5.0`, `detail_uppercase: false`) and `align: "center"` (`x_title == x_detail`):
- **Smokehouse / Heartland / County Fair / Americana (`rustic_heartland_americana`)**:
  - `title_font`: `Fraunces-Bold` (`scene_title_font`: `Bitter-Bold`)
  - `detail_font`: `Lora-BoldItalic` (`detail_size: 5.0`, `scene_detail_size: 5.0`, `detail_uppercase: false`)
  - Palette: Hickory Amber `#F5B85C` + Smoked Cream `#FAF3E6` + Honey Gold `#FFD485`
  - Flankers: `"—"` (characters), `"•"` (scene cards)
- **Coastal / Ocean / Lifeguard Rescue (`coastal_lifeguard_rescue`)**:
  - `title_font`: `Cinzel-Bold` (`scene_title_font`: `Optima-ExtraBlack`)
  - `detail_font`: `Lora-BoldItalic` (`detail_size: 5.0`, `scene_detail_size: 5.0`)
  - Palette: Sunlit Gold `#F4C86A` + Seafoam `#EBF7FA` + Surf Cyan `#9BE2F2`
  - Flankers: `"~"` (characters), `"•"` (scene cards)
- **Southern Gothic / Equestrian / Heritage Estate (`equestrian_heritage_estate`)**:
  - `title_font`: `PlayfairDisplay-Bold` (`end_title_font`: `Cinzel-Bold`)
  - `detail_font`: `CormorantGaramond-BoldItalic` (`detail_size: 5.0`, auto-boosted `1.14x` for low `xHeight`)
  - Palette: Heritage Gold `#F3CA6E` + Warm Parchment `#F6EFE2`
  - Flankers: `"—"` (characters), `"·"` (scene cards)
- **Legal / Courtroom / Corporate / Medical Dynasty (`legal_corporate_dynasty`)**:
  - `title_font`: `BodoniModa-Bold` (`scene_title_font`: `Didot-Bold`)
  - `detail_font`: `PlayfairDisplay-BoldItalic` (`detail_size: 5.0`)
  - Palette: Champagne Brass `#EED484` + Crisp Alabaster `#F2F5F8`
  - Flankers: `"—"` (characters), `"◇"` (scene cards)
- **Military / Aviation / Precinct / Tactical (`military_tactical_thriller`)**:
  - `title_font`: `Copperplate-Bold` (`scene_title_font`: `Cinzel-Bold`)
  - `detail_font`: `Optima-Bold` (`detail_size: 5.0`)
  - Palette: Platinum Silver `#EBF0F5` + Tactical Amber `#F2C45A`
  - Flankers: `"—"` (characters), `"•"` (scene cards)
- **High-Society / Gala / Symphony / Auction (`high_society_gala_drama`)**:
  - `title_font`: `DMSerifDisplay-Regular` (`scene_title_font`: `BodoniModa-Bold`)
  - `detail_font`: `PlayfairDisplay-BoldItalic` (`detail_size: 5.0`)
  - Palette: Rose Champagne `#F5D38C` + Velvet Ivory `#FAF5FF`
  - Flankers: `"« »"` (characters), `"◇"` (scene cards)
- **Modern Prestige Drama (`modern_prestige_drama`)**:
  - `title_font`: `LibreBaskerville-Bold`
  - `detail_font`: `Lora-BoldItalic` (`detail_size: 5.0`)
  - Palette: Warm Cinema Gold `#F2CC76` + Alabaster `#F5F2EB`
  - Flankers: `"—"` (characters), `"•"` (scene cards)

### Pillar B: Multi-Span Editorial Color Hierarchy (`styles[]` Contrast With Uniform `1.0x` Size)
`build_rich_text_content` automatically splits each text line into multi-span `styles[]` inside CapCut while preserving **`100%` uniform `style.font_size`** across all spans (because CapCut Desktop uses `styles[0]["size"]` as the base size of the text layer):
- **Title Line (`is_title=True`)**:
  - Honorific prefixes (`Dr. `, `Lt. `, `Capt. `, `Gen. `, `Judge `, `Sheikh `, `Sir `, `Lady `) and age/rank suffixes (`, 74`, ` — Age 15`) render in `accent_color_hex`, while the core name renders in `color_hex`.
- **Detail / Role / Time Line (`is_title=False`)**:
  - Structure role and scene strings with a separator (` · `, ` — `, ` & `):
    - Leading/trailing flankers (`~`, `—`, `•`, `◇`, `« »`) and the middle separator (` · `) render in `flanker_color`.
    - The primary role/time clause (before ` · `) renders in `detail_accent_color`.
    - The secondary affiliation/context clause (after ` · `) renders in `char_detail_color` / `time_detail_color`.

### Pillar C: Character Archetype Palette Accents (Per-Card Color Storytelling)
Use optional per-card `title_color` and `accent_color` overrides to reflect dramatic roles while staying within the film's `recommended_style` world palette:
- **Protagonist / Hero / Allies**: World primary warm accent (`#F5B85C`, `#F4C86A`, `#F3CA6E`) + warm cream (`#FAF3E6`).
- **Wealthy Antagonist / Rival**: Rose-champagne (`#F2C6CE`) or icy platinum (`#E2E8F0`).
- **Enforcer / Official / Cold Authority**: Cool steel-blue (`#B8CCE0`) or slate silver.

### Pillar D: Stack Order Contrast (`order` vs `scene_order`) & Staggered Entrance (`stagger_sec`)
- Use `"order": "title-first"` for character cards (Name on top, Role underneath) and `"scene_order": "detail-first"` for scene/location cards (Time/Context kicker on top, Location Title underneath).
- `stagger_sec` (default `0.10s`) delays the secondary line's fade-in by 3 frames after the primary line.

### Pillar E: Centered-Axis Symmetry (`align: "center"`)
- `"center"` locks `x_title == x_detail` on the exact same vertical center axis while anchoring the outer edge of the card block within safe screen bounds (`±0.88`).

## 2. Fast Starter Plan & Sub-Shot Timing (`< 5–15 Min` Total Workflow)

- `cards.py inspect` automatically writes `/tmp/inspect_<project>.json` (`< 800 lines`) AND generates `/tmp/plan_<project>.json` (`/tmp/starter_plan_<project>.json`) with sub-shot-locked `[start, end]` timestamps for all scenes, characters, and `THE END`.
- `cards.py probe` extracts sub-shot frames in `< 1s`, renders ONLY the `4x6` (`24`-frame) `probe_batch_01..NN.jpg` sheets, and updates `/tmp/plan_<project>.json` with negative-space-scored `anchor`s.
- View ONLY `probe_batch_01..NN.jpg` with `read_file` to verify faces and refine `/tmp/plan_<project>.json` before running `cards.py apply`.
- After running `cards.py apply`, open the paginated `preview_pages` (`preview_*_p1.jpg`, ...) with `read_file` to verify contrast, negative space, and hierarchy.
