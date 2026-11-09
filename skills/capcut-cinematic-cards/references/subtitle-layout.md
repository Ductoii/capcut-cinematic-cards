# In-Place Cinema Subtitle Styling & Screenplay-Grounded Normalization

When a CapCut project contains an existing Auto-Caption / subtitle track, style and normalize it in-place (`< 0.15s`) via the `"subtitles"` block in `plan.json`.

## 1. Subtitle Style Priority: User Request First, Classic Warm Yellow Default Otherwise

1. **When the User Requests a Specific Subtitle Style**:
   - Follow the user's explicit request or reference image (font family, condensed/serif/sans style, color, size, `y` position, stroke/shadow).
2. **When the User Does NOT Specify a Subtitle Style (`không req`)**:
   - Default to the classic **Warm Cinema Yellow Boxless** preset from `Custom Subtitle Styling And Font`:
     - `font`: `"Seravek-Medium"`
     - `size`: `4.2` (`text_size`: `30`)
     - `color`: `"#E5CE6E"`
     - `y`: `-0.78`
     - `stroke_color`: `"#0A0C0E"`, `stroke_width`: `0.028`, `stroke_alpha`: `0.95`
     - `shadow_color`: `"#050608"`, `shadow_alpha`: `0.82`, `shadow_smoothing`: `2.58`, `shadow_distance`: `1.8`, `shadow_diffuse`: `0.1435`
     - `check_flag`: `47`, `background_style`: `0` (boxless)

## 2. Automatic Screenplay-Grounded Subtitle Normalization (`normalize_with_screenplay: true`)

- **Never normalize subtitles blindly without the screenplay**.
- During `cards.py apply`, `build_screenplay_subtitle_context()` automatically loads `sf-board.json` (`shots[].text`, `scenes[].name`, `scenes[0].sfs[].label`) and any `*KICHBAN*.txt` in the project directory, then `_normalize_cue_with_screenplay()` aligns every subtitle cue `[start_s, end_s]` against the overlapping timeline shot's screenplay dialogue:
  - **2-Word Phonetic Fusions**: Fixes split ASR words against the shot's dialogue words (e.g., `life Lord` -> `lifeguard`).
  - **Contextual Neighbor Mishearings**: Fixes single-word ASR mishearings when the surrounding words match the screenplay dialogue (e.g., `vacate this Jack` -> `vacate this shack`, `Coral Reef` -> `Coral Reach`).
  - **Numbered Designations & Multi-Word Proper Phrases**: Restores exact screenplay terms (`claws 9` / `close 9` -> `Clause 9`, `stole 9` -> `Stall 9`).
  - **Character & Location Proper Nouns**: Restores exact screenplay casing (`alford` -> `Alford`, `wexler` -> `Wexler`, `wes` -> `Wes`) and fixes phonetic ASR typos of character names (`lanira` / `Lanissa` -> `Lenora`, `Whitlock` -> `Whitlow`, `Holloway` -> `Halloway`).
- You can also supply additional manual `word_replacements` or `cue_overrides` in `plan.json`:
  ```json
  "subtitles": {
    "style_in_place": true,
    "normalize_with_screenplay": true,
    "sentence_case": true,
    "font": "Seravek-Medium",
    "size": 4.2,
    "text_size": 30,
    "color": "#E5CE6E",
    "y": -0.78,
    "stroke_color": "#0A0C0E",
    "stroke_width": 0.028,
    "shadow_alpha": 0.82,
    "shadow_smoothing": 2.58,
    "shadow_distance": 1.8,
    "word_replacements": {},
    "cue_overrides": {}
  }
  ```
- Cues longer than `max_chars_per_line` (`42`) are automatically wrapped at the most balanced word boundary into 2 lines.
