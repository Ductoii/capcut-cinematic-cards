# CapCut Cinematic Cards & Subtitles (`v0.7.0`)

Language: [Tiếng Việt](README.md) | **English**

Zero-preset, AI-art-directed **Location, Time, Character, and `THE END` title cards** plus **screenplay-grounded in-place cinematic subtitles** for macOS CapCut Desktop drafts (`draft_info.json`), built on **YAGNI** (`inspect` -> `probe` -> `apply` + `preview_sheet` verification in `< 6 seconds` using 16-thread parallelism).

---

## Core Capabilities in `v0.7.0`

1. **16-Thread Parallel Pipeline (`< 6s` Cold Cache, `< 1.5s` Warm Cache) & Screenplay World Archetypes**:
   - Parallelizes `inspect` (`0.4s`), `probe` (`0.4s–5.6s`), and `apply + preview_pages` (`1.1s–3.4s`) across 16 worker threads with frame caching and in-memory font caching.
   - Automatically synthesizes a screenplay-matched `recommended_style` across 8 distinct cinema art-direction archetypes (`coastal_lifeguard_rescue`, `rustic_heartland_americana`, `legal_corporate_dynasty`, `military_tactical_thriller`, `high_society_gala_drama`, `equestrian_heritage_estate`, `modern_prestige_drama`) with a built-in Anti-Clone Guard.

2. **Screenplay-Grounded Subtitle Normalization & Classic Warm Cinema Yellow Default (`Seravek-Medium` `4.2` `#E5CE6E`)**:
   - Honors user-requested subtitle styles when specified, and defaults otherwise to the classic Warm Cinema Yellow Boxless preset (`Seravek-Medium`, `size: 4.2`, `text_size: 30`, `#E5CE6E`, `y: -0.78`, `stroke_width: 0.028`, `shadow_alpha: 0.82`, `shadow_smoothing: 2.58`, `shadow_distance: 1.8`, `check_flag: 47`).
   - Aligns every subtitle cue `[start_s, end_s]` against the overlapping timeline shot's screenplay dialogue (`sf-board.json` / `*KICHBAN*.txt`) to automatically fix split compound words (`life Lord` -> `lifeguard`), contextual neighbor mishearings (`vacate this Jack` -> `vacate this shack`, `Coral Reef` -> `Coral Reach`), numbered clauses (`claws 9` -> `Clause 9`), and character proper nouns (`lanira` -> `Lenora`, `alford` -> `Alford`).

3. **Multi-Span Editorial Rich Text (`styles[]`) & Glyph-Verified Flankers**:
   - Generates multi-span `styles[]` within a single CapCut text layer and wraps detail lines with glyph-verified ornamental flankers (`~`, `—`, `•`, `|`, `::`, `◇`).

4. **Automatic Glare/Signage Avoidance (`score_frame_negative_space`) & Native CapCut `Fade In` + `Fade Out`**:
   - Scores all 4 frame corners (`lower-left`, `lower-right`, `upper-left`, `upper-right`) to avoid bright white signage/glare and renders paginated `4x4` WYSIWYG preview sheets (`preview_<plan>_p1.jpg`, ...).

---

## Quick Install (`v0.7.0`)

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.7.0/install.py | python3
```
