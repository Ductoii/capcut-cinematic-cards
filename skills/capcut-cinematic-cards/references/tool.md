# CLI & `plan.json` Reference (`scripts/cards.py`)

## Subcommands

### 1. `inspect`
Unwraps both top-level and Compound Clip (`materials.drafts`) timelines, groups scenes, and extracts subtitles/cards.
```bash
python3 scripts/cards.py inspect "<project>" --out /tmp/inspect.json
```

### 2. `fonts` & `fetch-font`
Lists local macOS PostScript fonts + 1,600+ downloadable Google Fonts grouped by typographic family, or fetches and normalizes any Google Font on demand.
```bash
python3 scripts/cards.py fonts
python3 scripts/cards.py fetch-font "PlayfairDisplay-Bold" "CormorantGaramond-BoldItalic" "Cinzel-Bold"
```

### 3. `probe`
Runs `ffmpeg scdet` on candidate windows and generates labeled contact sheets.
```bash
python3 scripts/cards.py probe "<project>" --windows "0-40,170-190,347-370" --out /tmp/probe_out
```

### 4. `apply`
Applies `plan.json` to the CapCut project, syncs `draft_info.json`, `draft_content.json`, and `Timelines/*/draft_info.json`, clears stale `patch.json` / `mini_draft.json`, and renders a WYSIWYG preview contact sheet (`preview_<plan>.jpg`).
```bash
python3 scripts/cards.py apply "<project>" --plan /tmp/plan.json
```

---

## `plan.json` Schema

```json
{
  "style": {
    "title_font": "PlayfairDisplay-Bold",
    "detail_font": "CormorantGaramond-BoldItalic",
    "scene_title_font": "PlayfairDisplay-Bold",
    "scene_detail_font": "CormorantGaramond-BoldItalic",
    "end_title_font": "Cinzel-Bold",
    "end_detail_font": "CormorantGaramond-BoldItalic",
    "title_size": 6.8,
    "detail_size": 4.3,
    "scene_title_size": 6.6,
    "scene_detail_size": 4.1,
    "end_title_size": 8.0,
    "end_detail_size": 4.3,
    "char_title_color": "#F3CA6E",
    "char_detail_color": "#F6EFE2",
    "detail_accent_color": "#F2CE7E",
    "time_title_color": "#FBF5E8",
    "time_detail_color": "#EFE2C8",
    "scene_accent_color": "#F3CA6E",
    "flanker_color": "#D8B268",
    "flankers": "—",
    "scene_flankers": "·",
    "stagger_sec": 0.10,
    "align": "center",
    "order": "title-first",
    "scene_order": "detail-first",
    "stroke_color": "#0E0B08",
    "stroke_width": 0.015,
    "shadow_color": "#050403",
    "shadow_alpha": 0.94,
    "shadow_smoothing": 0.42,
    "shadow_distance": 2.4,
    "line_gap": 0.15
  },
  "cards": [
    {
      "kind": "scene",
      "start": 0.25,
      "end": 2.85,
      "title": "Auction Stable Yard",
      "detail": "Morning · Kentucky Thoroughbred Sale",
      "anchor": "lower-right"
    },
    {
      "kind": "char",
      "start": 50.55,
      "end": 54.35,
      "title": "Lorraine Ashby",
      "detail": "Syndicate Owner · Tamarack's Buyer",
      "title_color": "#F2C6CE",
      "accent_color": "#F2C6CE",
      "anchor": "lower-left"
    },
    {
      "kind": "char",
      "start": 91.68,
      "end": 94.79,
      "title": "Tamarack",
      "detail": "$5M Champion · Thoroughbred Stallion",
      "flankers": "« »",
      "anchor": "lower-right"
    },
    {
      "kind": "end",
      "start": 1658.40,
      "end": 1663.20,
      "title": "THE END",
      "detail": "Silverbrook Thoroughbred Farm",
      "anchor": "lower-center"
    }
  ],
  "subtitles": {
    "style_in_place": true,
    "font": "AvenirNext-Medium",
    "size": 4.2,
    "color": "#F5E6A8",
    "y": -0.78,
    "stroke_width": 0.024,
    "shadow_alpha": 0.90,
    "shadow_smoothing": 2.2,
    "word_replacements": {},
    "cue_overrides": {}
  }
}
```
