# CapCut Cinematic Cards & Subtitles (`v0.6.0`)

Language: [Tiếng Việt](README.md) | **English**

Zero-preset, AI-art-directed **Location, Time, Character, and `THE END` title cards** plus **zero-drift in-place cinematic subtitles** for macOS CapCut Desktop drafts (`draft_info.json`), built on **YAGNI** (`inspect` -> `probe` -> `apply` + `preview_sheet` verification in `< 6 seconds`).

---

## Core Capabilities in `v0.6.0`

1. **Zero Canned Presets & Automatic Google Fonts Fetching (`1,600+` Fonts)**:
   - Art-directs every film from scratch based on its screenplay (`inspect` + `sf-board.json`).
   - Extracts macOS `.ttc` faces or **downloads any Google Font on demand** (`PlayfairDisplay-Bold`, `CormorantGaramond-BoldItalic`, `Cinzel-Bold`, `BodoniModa-Bold`, `DMSerifDisplay-Regular`, `InstrumentSerif-Italic`, `Rye-Regular`, `BebasNeue-Regular`, `JetBrainsMono-SemiBold`), normalizes `hhea`/`OS/2` vertical metrics (`1.20 * upm`), and installs them into CapCut's sandbox container in `< 0.4s`.

2. **Multi-Span Editorial Rich Text (`styles[]`) & Glyph-Verified Flankers**:
   - Generates multi-span `styles[]` within a single CapCut text layer:
     - **Title Line**: Automatically styles honorific prefixes (`Dr. `, `Lt. `, `Judge `, `Sheikh `) and age suffixes (`, 74`) at `0.82–0.85x` size in `accent_color` while keeping the core name at `1.0x` in `title_color`.
     - **Detail / Role / Time Line**: Highlights the primary role/status badge (`$5M Champion`, `Stable Hand`, `Head Trainer`, `Morning`) in `detail_accent_color`, renders the secondary affiliation/context in `char_detail_color`, and wraps with ornamental flankers (`—`, `« »`, `·`, `[ ]`, `//`) verified against the font's Unicode `cmap`.

3. **Centered-Axis Symmetry (`align: "center"`) & Trim/Cut-Immune Timing**:
   - Locks `x_title == x_detail` on the exact same vertical center axis while anchoring the outer edge at `±0.88` using calibrated CapCut pixel widths (`11.2 px/em/size` on `1920x1080`).
   - Recursively unwraps trimmed/split `Compound Clips` (`materials.drafts`) with exact `source_timerange` intersection, projects `sf-board.json` shot breakdowns (`goc`) onto surviving timeline seconds (`TL x-ys` vs `TRIMMED_OUT`), and locks `[start_s, end_s]` inside a single continuous `scdet` camera sub-shot.

4. **Native CapCut `Fade In` + `Fade Out` (Staggered Entrance `0.10s`) & WYSIWYG Preview Sheet**:
   - Attaches native CapCut `sticker_animation` entries (`Fade In`: `6724916044072227332`, `Fade Out`: `6724919382104871427`, `start = segment_duration_us - fade_out_us`) with a `0.10s` secondary-line stagger, and renders `preview_<plan>.jpg` on actual video frames for visual verification.

---

## Quick Install (`v0.6.0`)

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.6.0/install.py | python3
```
