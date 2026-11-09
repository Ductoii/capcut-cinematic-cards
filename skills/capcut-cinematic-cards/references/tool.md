# CLI & `plan.json` Reference (`scripts/cards.py`)

## Subcommands

### 1. `inspect`
Unwraps both top-level and Compound Clip (`materials.drafts`) timelines, detects Cold-Open Hook teasers (`hook_window_s`), maps chronological story scenes and full character appearances (`all_scene_appearances` + subtitle-aligned `speaker_turns`), writes `/tmp/inspect_<project>_timeline.txt` (human/LLM-readable cheat sheet), and generates `/tmp/plan_<project>.json`.
```bash
python3 scripts/cards.py inspect "<project>" [--screenplay "/path/to/sf-board.json"] --out /tmp/inspect.json
```

### 2. `fonts` & `fetch-font`
Lists local macOS PostScript fonts + 1,600+ downloadable Google Fonts grouped by typographic family, or fetches and normalizes any Google Font on demand in parallel.
```bash
python3 scripts/cards.py fonts
python3 scripts/cards.py fetch-font "<TitleFont>" "<DetailFont>" "<SceneFont>"
```

### 3. `probe`
Extracts sub-shot boundaries and generates labeled contact sheets in parallel (`< 1.0s`).
```bash
python3 scripts/cards.py probe "<project>" --windows "<recommended_probe_windows>" --out /tmp/probe_out
```

### 4. `apply`
Applies `plan.json` to the CapCut project in `< 1.5s` (or `< 0.5s` with `--no-preview`), syncs `draft_info.json`, `draft_content.json`, and `Timelines/*/draft_info.json`, clears stale `patch.json` / `mini_draft.json`, automatically scores frame luminance to avoid bright signage/glare, normalizes subtitles against the screenplay (`sf-board.json` / `*KICHBAN*.txt`), and renders paginated WYSIWYG preview contact sheets (`preview_<plan>_p1.jpg`, ...).
```bash
python3 scripts/cards.py apply "<project>" --plan /tmp/plan.json --preview /tmp/preview.jpg
python3 scripts/cards.py apply "<project>" --plan /tmp/plan.json --no-preview
```

---

## `plan.json` Schema

> **IMPORTANT**: Always start from `"recommended_style"` in `/tmp/inspect_<project>.json` (computed from the screenplay's world archetype) or customize it for the specific film. If `"style"` is omitted, `apply` automatically uses `recommended_style`.

```json
{
  "outro_black_sec": 3.0,
  "style": "<Copy or customize `recommended_style` from /tmp/inspect_<project>.json — or omit `style` to auto-apply `recommended_style`>",
  "cards": [
    {
      "kind": "scene",
      "start": 10.25,
      "end": 13.85,
      "title": "<Location Title from Story Scene>",
      "detail": "<Time / Context Kicker>",
      "anchor": "auto"
    },
    {
      "kind": "char",
      "start": 24.50,
      "end": 28.20,
      "title": "<Character Name>",
      "detail": "<Character Role · Affiliation>",
      "anchor": "auto"
    },
    {
      "kind": "end",
      "start": 1658.40,
      "end": 1663.20,
      "title": "THE END",
      "detail": "<Final Setting or Epilogue Line>",
      "anchor": "lower-center",
      "hold_to_end": true
    }
  ],
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
    "stroke_alpha": 0.95,
    "shadow_color": "#050608",
    "shadow_alpha": 0.82,
    "shadow_smoothing": 2.58,
    "shadow_distance": 1.8,
    "shadow_diffuse": 0.1435,
    "word_replacements": {},
    "cue_overrides": {}
  }
}
```
