# In-Place Cinema Subtitle Styling (AI-Adaptive)

When a CapCut project contains an existing Auto-Caption / subtitle track, style it in-place (`< 0.2s`) via the `"subtitles"` block in `plan.json`.

## 1. Preserve Existing Timing & Style In-Place (`< 0.2s`)

- **Never delete or rebuild the subtitle track from scratch**.
- `style_subtitle_track_in_place` updates every subtitle segment and material in-place in `< 0.2s`, preserving CapCut's exact speech-synced `target_timerange`.

## 2. AI-Directed Subtitle Typography & Palette Per Screenplay

- Do **not** lock every film into a single font or color. Choose a clean, high-legibility subtitle font from `cards.py fonts` (`Seravek-Medium`, `AvenirNext-Medium`, `GillSans-SemiBold`, `Optima-Bold`, `HelveticaNeue-Medium`, `Charter-Bold`, etc.) and a fill color (`color`) that harmonizes with the film's color grade (e.g., warm cinema gold `#E5CE6E`, soft parchment `#F5E6A8`, crisp theatrical white `#FAF8F5`, or warm ivory `#FFF6E5`).
- Balance stroke (`stroke_width: 0.020..0.028`) and soft drop shadow (`shadow_alpha: 0.88..0.94`, `shadow_smoothing: 1.8..2.6`, `shadow_distance: 1.6..2.2`) so subtitles remain effortless to read over both bright and dark scenes (`check_flag = 47` when stroke > 0, `39` for shadow-only).

## 3. ASR Typo Fixes & Balanced 2-Line Wrapping

- Scan `subtitles` in `inspect.json` for ASR misspellings of character names or places from `character_appearances` / `story_scenes`, and pass `word_replacements` or `cue_overrides` in `plan.json`:
  ```json
  "subtitles": {
    "style_in_place": true,
    "font": "AvenirNext-Medium",
    "size": 4.2,
    "color": "#F5E6A8",
    "y": -0.78,
    "stroke_width": 0.024,
    "shadow_alpha": 0.90,
    "shadow_smoothing": 2.2,
    "word_replacements": {
      "Tamrack": "Tamarack",
      "Silver Brook": "Silverbrook"
    },
    "cue_overrides": {}
  }
  ```
- Cues longer than `max_chars_per_line` (`42`) are automatically wrapped at the most balanced word boundary into 2 lines.
