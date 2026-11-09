# AI Art Direction, Typography, Timing & Composition Guide

## 1. Cinema Visual Art Direction System (Zero Canned Templates)

Every film has its own world, lighting regime, and dramatic tension. Before writing `plan.json`, read the screenplay (`inspect` output / `sf-board.json`) and design the film's visual card language across **5 pillars**:

### Pillar A: World-Specific Font Pairing & Case/Alignment Matrix
Run `python3 scripts/cards.py fonts` or pass **any Google Font** (`<Family>-<Style>`) — `ensure_capcut_font()` auto-downloads and normalizes metrics (`1.20 * upm`) on the fly. **Never reuse the same font pair + alignment + flankers across different movies**:
- **Smokehouse / Heartland / Blue-Collar Resilience / Americana**:
  - `title_font`: `Fraunces-Bold` or `Bitter-Bold` (`scene_title_font`: `Bitter-Bold` or `Arvo-Bold`)
  - `detail_font`: `SpaceGrotesk-SemiBold` or `PlusJakartaSans-SemiBold` (`detail_uppercase: true`, `detail_letter_spacing: 0.05`, `detail_size: 3.5`)
  - `align`: `"outer"` (left cards flush-left at `-0.88`, right cards flush-right at `+0.88`)
  - `flankers`: `""` (characters), `"[ ]"` (scene cards)
- **Southern Gothic / Equestrian / Heritage Estate Drama**:
  - `title_font`: `PlayfairDisplay-Bold` or `DMSerifDisplay-Regular`
  - `detail_font`: `InstrumentSerif-Italic` or `CormorantGaramond-BoldItalic` (`detail_uppercase: false`, `detail_size: 4.2`)
  - `align`: `"center"`
  - `flankers`: `"—"` (characters), `"·"` (scene cards)
- **High-Society / Luxury Dynasty / Old-Money Intrigue / Fashion**:
  - `title_font`: `BodoniModa-Bold`, `Cinzel-Bold`, or `Didot-Bold`
  - `detail_font`: `CormorantGaramond-SemiBoldItalic` or `PlayfairDisplay-Italic`
  - `align`: `"center"`
  - `flankers`: `"« »"` or `"—"`
- **Military / Aviation / Naval / Tactical Thriller / Espionage**:
  - `title_font`: `BebasNeue-Regular`, `Oswald-Bold`, or `Rajdhani-Bold` (`title_letter_spacing: 0.04..0.06`)
  - `detail_font`: `JetBrainsMono-SemiBold` or `ChakraPetch-SemiBold` (`detail_uppercase: true`, `detail_letter_spacing: 0.06`)
  - `align`: `"outer"`
  - `flankers`: `"//"` or `"[ ]"`
- **Investigative / Courtroom / True Crime / Historical Dossier**:
  - `title_font`: `LibreBaskerville-Bold` or `DMSerifDisplay-Regular`
  - `detail_font`: `CourierPrime-Bold` or `SpecialElite-Regular` (`detail_uppercase: true`, `detail_letter_spacing: 0.04`)
  - `align`: `"outer"`
  - `flankers`: `"[ ]"` or `"—"`
- **Modern Prestige A24 / Indie Drama**:
  - `title_font`: `InstrumentSerif-Regular` or `Syne-Bold`
  - `detail_font`: `PlusJakartaSans-SemiBold` (`detail_uppercase: true`, `detail_letter_spacing: 0.05`)
  - `align`: `"outer"`
  - `flankers`: `""` or `"·"`

### Pillar B: Multi-Span Editorial Rich Text (`styles[]` Contrast Inside Each Line)
A single flat color across an entire line looks plain ("một màu"). `build_rich_text_content` automatically splits each text line into multi-span `styles[]` inside CapCut:
- **Title Line (`is_title=True`)**:
  - Honorific prefixes (`Dr. `, `Lt. `, `Capt. `, `Gen. `, `Judge `, `Sheikh `, `Sir `, `Lady `) and age/rank suffixes (`, 74`, ` — Age 15`) are automatically rendered at `0.82–0.85x` font size in `accent_color_hex`, while the core name renders at `1.0x` in `color_hex`.
- **Detail / Role / Time Line (`is_title=False`)**:
  - Structure role and scene strings with a separator (` · `, ` — `, ` & `) or a leading status badge (`Senior Lifeguard`, `Four-Star General`, `Founder`):
    - Leading/trailing flankers (`~`, `—`, `•`, `|`, `::`) and the middle separator (` · `) render in `flanker_color` at `0.88x` size.
    - The primary role/time clause (before ` · `) or leading badge renders in `detail_accent_color`.
    - The secondary affiliation/context clause (after ` · `) renders in `char_detail_color`.

### Pillar C: Character Archetype Palette Accents (Per-Card Color Storytelling)
Instead of coloring every character identically, use per-card `title_color` and `accent_color` overrides to reflect each character's dramatic role while staying within the film's `recommended_style` world palette:
- **Protagonist / Hero / Allies**: World primary warm accent (`#F4C86A`, `#EED484`, `#F4B860`) + crisp secondary (`#D9EFF7`, `#E4EBF2`).
- **Wealthy Antagonist / Syndicate / Rival**: Rose-champagne (`#F2C6CE` / `#EAB8C2`) or icy platinum (`#E2E8F0`).
- **Enforcer / Corrupt Official / Cold Authority**: Cool steel-blue (`#B8CCE0` / `#94D2BD`) or slate silver.
- **Elder Matriarch / Judge / Commission Steward**: Antique champagne-gold (`#EAD49B`) + parchment (`#F7F0E4`).

### Pillar D: Stack Order Contrast (`order` vs `scene_order`) & Staggered Entrance (`stagger_sec`)
- Use `"order": "title-first"` for character cards (Name on top, Role underneath) and `"scene_order": "detail-first"` (or `"title-first"` depending on the archetype) for scene/location cards so the viewer's eye immediately distinguishes a character introduction from a scene transition.
- `stagger_sec` (default `0.10s`) automatically delays the secondary line's fade-in by 3 frames after the primary line, giving every card a smooth, editorial two-beat entrance.

### Pillar E: Centered-Axis Symmetry (`align: "center"`)
- `"center"` (Default & Enforced for `"auto"` / `"outer"` / `"center"`): Locks `x_title == x_detail` on the exact same vertical center axis while anchoring the outer edge of the card block at `±0.88`. Because CapCut center-anchors each text box around `transform.x` and renders multi-span sizes (`0.85x`/`0.88x`) with non-linear FreeType kerning, `x_title == x_detail` is the ONLY alignment that guarantees 100% sub-pixel symmetry in CapCut without crooked horizontal drift.
- Always pair a Classical Editorial Serif Title (`PlayfairDisplay-Bold`, `Cinzel-Bold`, `Baskerville-Bold`, `BodoniModa-Bold`, `DMSerifDisplay-Regular`) with a Mixed-Case Calligraphic Italic Serif Detail (`CormorantGaramond-BoldItalic`, `CormorantGaramond-SemiBoldItalic`, `InstrumentSerif-Italic`, `detail_uppercase: false`) and cinema flankers (`"—"` for characters, `"·"` for scenes). Never use ALL-CAPS sans-serif (`SpaceGrotesk-SemiBold` + `detail_uppercase: true`) or `[ ]` brackets on narrative drama cards.

## 2. Ground-Truth Character & Scene Timing (Zero Drift)

- `cards.py inspect` automatically discovers `sf-board.json` from the video paths and outputs:
  - `story_scenes`: Exact `[start_s, end_s]` and opening clip `V-NNN` for every screenplay scene (`S01..SNN`).
  - `character_appearances`: Every character (`CHAR1..CHARN`, `AL1..ALN`) mapped to their **exact first 2 clips (`V-NNN`)**, timeline seconds `[start_s, end_s]`, and `shot_breakdown` (`goc`).
  - `recommended_probe_windows`: Ready-to-run `--windows` string for `cards.py probe`.
- Always pass the candidate windows to `cards.py probe` and view the contact sheets (`sheet_*.jpg`) with `read_file` to pick the exact sub-shot `[start_s, end_s]` where the character is clearly visible on camera (`2.5s–4.2s`).
- During `apply`, **Full Sub-Shot Boundary Locking** automatically checks `ffmpeg scdet` + segment cuts in `[start_s - 0.6s, end_s + 0.6s]` and locks both `start_s >= shot_lo + 0.15s` and `end_s <= shot_hi - 0.08s` so no card ever starts before a cut or bleeds into the next shot.

## 3. Negative-Space Placement & Visual Verification (`preview_sheet`)

- Place each card in the cleanest dark/uncluttered region of its specific frame (`lower-left`, `lower-right`, `upper-left`, `upper-right`, `mid-left`, `mid-right`, `lower-center`, `upper-center`, `center`).
- When two named characters appear together in a two-shot, place both cards simultaneously (`lower-left` and `lower-right`); `cards.py` automatically creates `Cinematic Cards · Main 2` / `Detail 2`.
- After running `cards.py apply`, **always open the generated `preview_sheet` (`preview_*.jpg`) with `read_file`** to verify contrast, negative space, and hierarchy with your own eyes.
